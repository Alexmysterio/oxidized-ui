from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .backup_service import run_backup_all_job
from .errors import AppError
from .jobs import create_and_submit
from .models import BackupSchedule, Job, Node
from .timeutil import utcnow


def serialize(row: BackupSchedule) -> dict[str, Any]:
    return {
        "id": row.id,
        "group_name": row.group_name,
        "interval_minutes": row.interval_minutes,
        "enabled": row.enabled,
        "next_run_at": row.next_run_at.isoformat() if row.next_run_at else None,
        "last_run_at": row.last_run_at.isoformat() if row.last_run_at else None,
    }


def count_nodes(db: Session, group_name: str | None) -> int:
    query = select(func.count(Node.id))
    if group_name:
        query = query.where(Node.group_name == group_name)
    return int(db.scalar(query) or 0)


def create_schedule(db: Session, *, group_name: str | None, interval_minutes: int, actor_id: int) -> BackupSchedule:
    if interval_minutes < 15:
        raise AppError("validation.range", params={"field": "interval_minutes", "min": 15})
    existing = db.scalar(select(BackupSchedule).where(BackupSchedule.group_name == group_name))
    if existing is not None:
        raise AppError("validation.duplicate", params={"field": "group_name"})
    row = BackupSchedule(
        group_name=group_name,
        interval_minutes=interval_minutes,
        next_run_at=utcnow() + timedelta(minutes=interval_minutes),
        created_by_id=actor_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def delete_schedule(db: Session, schedule_id: int) -> None:
    row = db.get(BackupSchedule, schedule_id)
    if row is None:
        raise AppError("app.not_found", params={"id": schedule_id})
    db.delete(row)
    db.commit()


def update_schedule(
    db: Session,
    schedule_id: int,
    *,
    group_name: str | None = None,
    interval_minutes: int | None = None,
    enabled: bool | None = None,
    group_name_set: bool = False,
) -> BackupSchedule:
    row = db.get(BackupSchedule, schedule_id)
    if row is None:
        raise AppError("app.not_found", params={"id": schedule_id})
    if group_name_set:
        existing = db.scalar(
            select(BackupSchedule).where(
                BackupSchedule.group_name == group_name, BackupSchedule.id != schedule_id
            )
        )
        if existing is not None:
            raise AppError("validation.duplicate", params={"field": "group_name"})
        row.group_name = group_name
    if interval_minutes is not None:
        if interval_minutes < 15:
            raise AppError("validation.range", params={"field": "interval_minutes", "min": 15})
        row.interval_minutes = interval_minutes
        row.next_run_at = utcnow() + timedelta(minutes=interval_minutes)
    if enabled is not None:
        row.enabled = bool(enabled)
        if row.enabled and row.next_run_at is None:
            row.next_run_at = utcnow() + timedelta(minutes=row.interval_minutes)
    db.commit()
    db.refresh(row)
    return row


def run_due(db: Session) -> int:
    from .maintenance_service import scoped_node_ids

    due = db.scalars(
        select(BackupSchedule).where(BackupSchedule.enabled.is_(True), BackupSchedule.next_run_at <= utcnow())
    ).all()
    started = 0
    maintenance = scoped_node_ids(db)
    for row in due:
        query = select(Node)
        if row.group_name:
            query = query.where(Node.group_name == row.group_name)
        nodes = [node for node in db.scalars(query).all() if node.id not in maintenance]
        now = utcnow()
        launched = False
        active = db.scalar(
            select(Job).where(Job.kind == "backup_all", Job.status.in_(("queued", "running")))
        )
        if nodes and active is None:
            create_and_submit(
                db,
                kind="backup_all",
                actor_id=row.created_by_id,
                payload={"node_ids": [node.id for node in nodes], "count": len(nodes), "schedule_id": row.id},
                progress_total=len(nodes),
                runner=run_backup_all_job,
            )
            started += 1
            launched = True
        if launched:
            row.last_run_at = now
            row.next_run_at = now + timedelta(minutes=row.interval_minutes)
        else:
            # Another bulk backup is running (or the group is empty): retry shortly
            # instead of reporting a run that never happened.
            retry = 5 if nodes else row.interval_minutes
            row.next_run_at = now + timedelta(minutes=retry)
        db.commit()
    return started
