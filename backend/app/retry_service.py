from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .jobs import create_and_submit
from .maintenance_service import scoped_node_ids
from .models import Job, Node, NodeRetry, NodeStatusCache
from .serializers import status_bucket
from .system_service import ensure_system_settings
from .timeutil import ensure_utc, utcnow

MAX_DELAY_MINUTES = 360


def _retry_delay(base_minutes: int, attempts: int) -> int:
    return min(MAX_DELAY_MINUTES, max(1, base_minutes) * (2 ** max(0, attempts - 1)))


def _failure_nodes(db: Session) -> list[tuple[Node, NodeStatusCache]]:
    caches = {cache.node_id: cache for cache in db.scalars(select(NodeStatusCache)).all()}
    result: list[tuple[Node, NodeStatusCache]] = []
    for node in db.scalars(select(Node)).all():
        cache = caches.get(node.id)
        if cache is None:
            continue
        bucket = status_bucket(cache.status, cache.last_success_at, cache.last_failure_at)
        if bucket == "failed":
            result.append((node, cache))
    return result


def plan_retries(db: Session) -> int:
    """Create or reset retry rows for nodes whose latest outcome was a failure."""
    settings_row = ensure_system_settings(db)
    if not settings_row.retry_failed_enabled:
        return 0
    now = utcnow()
    base = int(settings_row.retry_base_minutes or 15)
    failing = _failure_nodes(db)
    failing_ids = {node.id for node, _ in failing}
    rows = {row.node_id: row for row in db.scalars(select(NodeRetry)).all()}
    changed = 0

    for node_id, row in rows.items():
        if node_id not in failing_ids:
            db.delete(row)
            changed += 1

    for node, cache in failing:
        failure_at = ensure_utc(cache.last_failure_at)
        success_at = ensure_utc(cache.last_success_at)
        if failure_at is None or (success_at is not None and failure_at <= success_at):
            continue
        row = rows.get(node.id)
        if row is None:
            db.add(
                NodeRetry(
                    node_id=node.id,
                    attempts=0,
                    next_attempt_at=now + timedelta(minutes=base),
                    failure_at=failure_at,
                )
            )
            changed += 1
            continue
        if ensure_utc(row.failure_at) != failure_at:
            row.failure_at = failure_at
            row.attempts = 0
            row.exhausted_notified = False
            row.next_attempt_at = now + timedelta(minutes=base)
            changed += 1
    if changed:
        db.commit()
    return changed


def run_due_retries(db: Session) -> int:
    from .notifications import notify_retry_exhausted

    settings_row = ensure_system_settings(db)
    if not settings_row.retry_failed_enabled:
        return 0
    now = utcnow()
    base = int(settings_row.retry_base_minutes or 15)
    max_attempts = int(settings_row.retry_max_attempts or 3)
    maintenance = scoped_node_ids(db)
    started = 0
    rows = list(db.scalars(select(NodeRetry).where(NodeRetry.next_attempt_at <= now)).all())
    for row in rows:
        node = db.get(Node, row.node_id)
        cache = db.get(NodeStatusCache, row.node_id)
        if node is None or cache is None:
            db.delete(row)
            db.commit()
            continue
        bucket = status_bucket(cache.status, cache.last_success_at, cache.last_failure_at)
        if bucket != "failed":
            db.delete(row)
            db.commit()
            continue
        if node.id in maintenance:
            row.next_attempt_at = now + timedelta(minutes=5)
            db.commit()
            continue
        if row.attempts >= max_attempts:
            if not row.exhausted_notified:
                notify_retry_exhausted(db, node.name, row.attempts)
                row.exhausted_notified = True
            row.next_attempt_at = now + timedelta(minutes=MAX_DELAY_MINUTES)
            db.commit()
            continue
        active = db.scalar(
            select(Job).where(Job.node_id == node.id, Job.status.in_(("queued", "running")))
        )
        if active is not None:
            row.next_attempt_at = now + timedelta(minutes=5)
            db.commit()
            continue
        create_and_submit(
            db,
            kind="backup_node",
            actor_id=None,
            payload={"node_id": node.id, "name": node.name, "retry": row.attempts + 1},
            node_id=node.id,
            progress_total=1,
            runner=_run_node_backup,
        )
        row.attempts += 1
        row.last_error = cache.status
        row.next_attempt_at = now + timedelta(minutes=_retry_delay(base, row.attempts))
        db.commit()
        started += 1
    return started


def _run_node_backup(db: Session, job: Job) -> dict[str, object]:
    from .backup_service import run_backup_node_job

    return run_backup_node_job(db, job)


def retry_public(db: Session, node_id: int) -> dict[str, object] | None:
    row = db.get(NodeRetry, node_id)
    if row is None:
        return None
    return {
        "attempts": row.attempts,
        "next_attempt_at": row.next_attempt_at.isoformat() if row.next_attempt_at else None,
        "exhausted": bool(row.exhausted_notified),
    }
