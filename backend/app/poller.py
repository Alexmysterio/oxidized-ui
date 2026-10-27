from __future__ import annotations

import hashlib
import logging
import threading
from datetime import datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .backup_schedule_service import run_due as run_due_backups
from .config_alert_service import detect_config_changes
from .config_service import run_due_scheduled
from .db import SessionLocal
from .errors import AppError
from .export_service import run_due_export
from .health_service import snapshot as health_snapshot
from .maintenance_service import scoped_node_ids
from .models import AuditLog, BackupRun, Job, LoginAttempt, Node, NodeStatusCache
from .node_service import update_status_cache
from .notifications import notify_health, notify_stale, send_due_digests
from .oxidized import OxidizedNode
from .oxidized import client_for as oxidized_client_for
from .report_service import run_due_report
from .retry_service import plan_retries, run_due_retries
from .serializers import status_bucket
from .system_service import ensure_system_settings, ensure_system_state
from .timeutil import ensure_utc, utcnow

logger = logging.getLogger("oxidized_ui.poller")

_stop = threading.Event()
_thread: threading.Thread | None = None


def start_poller() -> None:
    global _thread
    if _thread is not None and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_loop, name="oxidized-poller", daemon=True)
    _thread.start()


def stop_poller() -> None:
    _stop.set()
    if _thread is not None:
        _thread.join(timeout=5)


def _loop() -> None:
    while not _stop.is_set():
        try:
            with SessionLocal() as db:
                refresh_status(db)
                run_due_scheduled(db)
                run_due_backups(db)
                plan_retries(db)
                run_due_retries(db)
                run_due_export(db)
                check_stale_backups(db)
                check_health(db)
                run_due_report(db)
                send_due_digests(db)
                cleanup_retention(db)
                settings_row = ensure_system_settings(db)
                interval = max(5, int(settings_row.poll_interval_seconds or 30))
        except Exception:  # noqa: BLE001 - background loop must survive
            logger.exception("Status poller iteration failed")
            interval = 30
        _stop.wait(interval)


_stale_sent: dict[int, datetime] = {}


_last_retention: datetime | None = None


def cleanup_retention(db: Session) -> None:
    global _last_retention
    now = utcnow()
    if _last_retention is not None and now - _last_retention < timedelta(hours=6):
        return
    row = ensure_system_settings(db)
    audit_days = max(7, int(row.audit_retention_days or 180))
    db.execute(delete(AuditLog).where(AuditLog.created_at < now - timedelta(days=audit_days)))
    db.execute(delete(Job).where(Job.finished_at.is_not(None), Job.finished_at < now - timedelta(days=30)))
    db.execute(delete(LoginAttempt).where(LoginAttempt.created_at < now - timedelta(days=30)))
    db.commit()
    _last_retention = now


_last_health: datetime | None = None


def check_health(db: Session) -> None:
    global _last_health
    row = ensure_system_settings(db)
    if not row.health_alerts_enabled:
        return
    now = utcnow()
    if _last_health is not None and now - _last_health < timedelta(hours=1):
        return
    _last_health = now
    snapshot = health_snapshot(db)
    if snapshot.get("warnings"):
        notify_health(
            db,
            list(snapshot["warnings"]),
            float(snapshot["disk"]["percent"]),
            int(snapshot["output_bytes"]),
        )


def check_stale_backups(db: Session) -> None:
    from datetime import timedelta

    from .system_service import ensure_system_settings
    from .timeutil import utcnow

    hours = int(ensure_system_settings(db).notify_stale_hours or 0)
    if hours <= 0:
        return
    cutoff = utcnow() - timedelta(hours=hours)
    now = utcnow()
    maintenance = scoped_node_ids(db)
    rows = db.execute(select(NodeStatusCache, Node).join(Node, Node.id == NodeStatusCache.node_id)).all()
    for cache, node in rows:
        if node.id in maintenance:
            continue
        if cache.last_success_at is None or ensure_utc(cache.last_success_at) > cutoff:
            continue
        last_sent = _stale_sent.get(node.id)
        if last_sent is not None and now - last_sent < timedelta(hours=6):
            continue
        if notify_stale(db, node.name, hours):
            _stale_sent[node.id] = now


def _dedupe_key(node: OxidizedNode) -> str:
    raw = f"{node.name}|{ensure_utc(node.last_started)}|{ensure_utc(node.last_finished)}|{node.status}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def refresh_status(db: Session) -> int:
    client = oxidized_client_for(db)
    try:
        live_nodes = client.list_nodes()
    except AppError:
        logger.debug("Oxidized API unavailable while polling status")
        return 0
    apply_live_nodes(db, live_nodes)
    try:
        detect_config_changes(db, live_nodes)
    except Exception:  # noqa: BLE001 - change detection must not stop status polling
        logger.exception("Configuration change detection failed")
    return len(live_nodes)


def apply_live_nodes(db: Session, live_nodes: list[OxidizedNode]) -> None:
    state = ensure_system_state(db)
    state.last_oxidized_seen_at = utcnow()
    by_name = {node.name: node for node in db.scalars(select(Node)).all()}
    for live in live_nodes:
        db_node = by_name.get(live.name)
        if db_node is None:
            continue
        update_status_cache(db, db_node, live)
        if live.last_finished is None and live.last_started is None:
            continue
        existing = db.scalar(select(BackupRun).where(BackupRun.dedupe_key == _dedupe_key(live)))
        if existing is None:
            started = ensure_utc(live.last_started) or ensure_utc(live.last_finished) or utcnow()
            finished = ensure_utc(live.last_finished)
            db.add(
                BackupRun(
                    node_id=db_node.id,
                    node_name=db_node.name,
                    group_name=live.group,
                    started_at=started,
                    finished_at=finished,
                    duration_seconds=int(live.last_time) if live.last_time is not None else None,
                    status=live.status or "unknown",
                    trigger="observed",
                    dedupe_key=_dedupe_key(live),
                    observed_at=utcnow(),
                )
            )
    db.commit()
    _prune_status_data(db)


def _prune_status_data(db: Session) -> None:
    settings_row = ensure_system_settings(db)
    days = int(settings_row.activity_retention_days or 0)
    if days <= 0:
        return
    cutoff = utcnow() - timedelta(days=days)
    db.execute(delete(BackupRun).where(BackupRun.finished_at.is_not(None), BackupRun.finished_at < cutoff))
    db.execute(delete(BackupRun).where(BackupRun.finished_at.is_(None), BackupRun.observed_at < cutoff))
    db.commit()


def status_snapshot(db: Session) -> dict[str, int]:
    nodes = db.scalars(select(Node)).all()
    caches = {cache.node_id: cache for cache in db.scalars(select(NodeStatusCache)).all()}
    counts = {"total": len(nodes), "ok": 0, "failed": 0, "pending": 0, "never": 0}
    for node in nodes:
        cache = caches.get(node.id)
        bucket = status_bucket(
            cache.status if cache else None,
            cache.last_success_at if cache else None,
            cache.last_failure_at if cache else None,
        )
        counts[bucket] += 1
    return counts


def recent_activity(db: Session, days: int) -> list[dict[str, object]]:
    cutoff = (utcnow() - timedelta(days=days)).date()
    rows = db.scalars(select(BackupRun).where(BackupRun.finished_at.is_not(None))).all()
    buckets: dict[str, dict[str, int]] = {}
    for row in rows:
        finished = ensure_utc(row.finished_at)
        if finished is None or finished.date() < cutoff:
            continue
        day = finished.date().isoformat()
        bucket = buckets.setdefault(day, {"success": 0, "failed": 0})
        if row.status == "success":
            bucket["success"] += 1
        else:
            bucket["failed"] += 1
    result: list[dict[str, object]] = []
    for offset in range(days - 1, -1, -1):
        day = (utcnow() - timedelta(days=offset)).date().isoformat()
        bucket = buckets.get(day, {"success": 0, "failed": 0})
        result.append({"date": day, "success": bucket["success"], "failed": bucket["failed"]})
    return result
