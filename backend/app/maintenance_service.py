from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .errors import AppError
from .models import MaintenanceWindow, Node
from .security import AuthContext
from .timeutil import ensure_utc, utcnow

SCOPE_TYPES = ("node", "group", "global")


def serialize(row: MaintenanceWindow, node_name: str | None = None) -> dict[str, Any]:
    now = utcnow()
    starts = ensure_utc(row.starts_at)
    ends = ensure_utc(row.ends_at)
    return {
        "id": row.id,
        "scope_type": row.scope_type,
        "node_id": row.node_id,
        "node_name": node_name,
        "group_name": row.group_name,
        "starts_at": row.starts_at.isoformat() if row.starts_at else None,
        "ends_at": row.ends_at.isoformat() if row.ends_at else None,
        "reason": row.reason,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "active": bool(starts and ends and starts <= now < ends),
    }


def list_windows(db: Session, *, include_finished: bool = False) -> list[dict[str, Any]]:
    query = select(MaintenanceWindow).order_by(MaintenanceWindow.starts_at.desc())
    rows = list(db.scalars(query).all())
    now = utcnow()
    names = {node.id: node.name for node in db.scalars(select(Node)).all()}
    result = []
    for row in rows:
        ends = ensure_utc(row.ends_at)
        if not include_finished and ends is not None and ends < now:
            continue
        result.append(serialize(row, names.get(row.node_id) if row.node_id else None))
    return result


def active_windows(db: Session, *, now: datetime | None = None) -> list[MaintenanceWindow]:
    moment = now or utcnow()
    rows = db.scalars(select(MaintenanceWindow)).all()
    return [
        row
        for row in rows
        if (starts := ensure_utc(row.starts_at)) is not None
        and (ends := ensure_utc(row.ends_at)) is not None
        and starts <= moment < ends
    ]


def scoped_node_ids(db: Session, windows: list[MaintenanceWindow] | None = None) -> set[int]:
    rows = windows if windows is not None else active_windows(db)
    if not rows:
        return set()
    nodes = list(db.scalars(select(Node)).all())
    if any(row.scope_type == "global" for row in rows):
        return {node.id for node in nodes}
    groups = {row.group_name for row in rows if row.scope_type == "group" and row.group_name}
    direct = {row.node_id for row in rows if row.scope_type == "node" and row.node_id}
    return {node.id for node in nodes if node.id in direct or node.group_name in groups}


def node_in_maintenance(db: Session, node: Node, *, now: datetime | None = None) -> bool:
    for row in active_windows(db, now=now):
        if row.scope_type == "global":
            return True
        if row.scope_type == "group" and row.group_name and row.group_name == node.group_name:
            return True
        if row.scope_type == "node" and row.node_id == node.id:
            return True
    return False


def create_window(
    db: Session,
    *,
    scope_type: str,
    node_id: int | None,
    group_name: str | None,
    starts_at: datetime,
    ends_at: datetime,
    reason: str | None,
    actor: AuthContext,
) -> MaintenanceWindow:
    if scope_type not in SCOPE_TYPES:
        raise AppError("validation.invalid_choice", params={"field": "scope_type"})
    starts = ensure_utc(starts_at)
    ends = ensure_utc(ends_at)
    if starts is None or ends is None or ends <= starts:
        raise AppError("validation.invalid_format", params={"field": "ends_at"})
    if scope_type == "node":
        node = db.get(Node, node_id) if node_id else None
        if node is None:
            raise AppError("node.not_found", params={"node_id": node_id})
        actor_scope = actor.scope_groups
        if actor_scope is not None and node.group_name not in actor_scope:
            raise AppError("auth.forbidden")
        group_name = node.group_name
    elif scope_type == "group":
        if not group_name:
            raise AppError("validation.required", params={"field": "group_name"})
        if actor.scope_groups is not None and group_name not in actor.scope_groups:
            raise AppError("auth.forbidden")
        node_id = None
    else:
        if actor.scope_groups is not None:
            raise AppError("auth.forbidden")
        node_id = None
        group_name = None
    row = MaintenanceWindow(
        scope_type=scope_type,
        node_id=node_id,
        group_name=group_name,
        starts_at=starts,
        ends_at=ends,
        reason=(reason or "").strip()[:255] or None,
        created_by_id=actor.user_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def delete_window(db: Session, window_id: int) -> None:
    row = db.get(MaintenanceWindow, window_id)
    if row is None:
        raise AppError("app.not_found", params={"id": window_id})
    db.delete(row)
    db.commit()
