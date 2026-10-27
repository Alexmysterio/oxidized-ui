from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .errors import AppError
from .models import MaintenanceWindow, Node, User
from .security import AuthContext


def scoped_groups(ctx: AuthContext) -> set[str] | None:
    if ctx.role == "admin":
        return None
    return set(ctx.scope_groups) if ctx.scope_groups else None


def require_group(ctx: AuthContext, group_name: str | None) -> None:
    scope = scoped_groups(ctx)
    if scope is None:
        return
    if not group_name or group_name not in scope:
        raise AppError("auth.forbidden")


def node_ids_in_scope(db: Session, ctx: AuthContext) -> set[int] | None:
    scope = scoped_groups(ctx)
    if scope is None:
        return None
    return {node.id for node in db.scalars(select(Node)).all() if node.group_name in scope}


def node_visible(ctx: AuthContext, node: Node) -> bool:
    scope = scoped_groups(ctx)
    return scope is None or (node.group_name is not None and node.group_name in scope)


def scoped_node(db: Session, ctx: AuthContext, node_id: int) -> Node:
    from .node_service import get_node

    node = get_node(db, node_id)
    if not node_visible(ctx, node):
        raise AppError("node.not_found", params={"node_id": node_id})
    return node


def visible_groups(ctx: AuthContext) -> list[str] | None:
    scope = scoped_groups(ctx)
    return sorted(scope) if scope is not None else None


def validate_scope_groups(db: Session, groups: list[str] | None) -> list[str] | None:
    if groups is None:
        return None
    cleaned = [group.strip() for group in dict.fromkeys(groups) if group and group.strip()]
    if not cleaned:
        return None
    known = {node.group_name for node in db.scalars(select(Node)).all() if node.group_name}
    unknown = sorted(group for group in cleaned if group not in known)
    if unknown:
        raise AppError("group.not_found", params={"name": unknown[0]})
    return cleaned


def context_scope(user: User) -> list[str] | None:
    scope = user.scope_groups
    if not scope:
        return None
    return [str(group) for group in scope]


def favorite_ids(db: Session, user_id: int) -> set[int]:
    from .models import UserPreference

    row = db.get(UserPreference, user_id)
    if row is None:
        return set()
    return {int(value) for value in (row.favorites or [])}


def ensure_scope_covers_windows(db: Session, ctx: AuthContext, window: MaintenanceWindow) -> None:
    scope = scoped_groups(ctx)
    if scope is None:
        return
    if window.scope_type == "global":
        raise AppError("auth.forbidden")
    if window.scope_type == "group" and window.group_name not in scope:
        raise AppError("auth.forbidden")
    if window.scope_type == "node":
        node = db.get(Node, window.node_id) if window.node_id else None
        if node is None or node.group_name not in scope:
            raise AppError("auth.forbidden")
