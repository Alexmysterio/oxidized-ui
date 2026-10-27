from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config_service import applied_config
from .docker_api import client_for as docker_client_for
from .errors import AppError
from .models import BackupRun, Job, Node, NodeStatusCache
from .oxidized import client_for as oxidized_client_for
from .poller import apply_live_nodes, recent_activity
from .serializers import status_bucket
from .system_service import ensure_system_settings, ensure_system_state
from .timeutil import ensure_utc, to_iso, utcnow


def _active_job_node_ids(db: Session, jobs: list[Job]) -> set[int]:
    result: set[int] = set()
    for job in jobs:
        if job.node_id is not None:
            result.add(job.node_id)
        if job.kind == "backup_all":
            for value in job.payload.get("node_ids", []) if isinstance(job.payload, dict) else []:
                try:
                    result.add(int(value))
                except (TypeError, ValueError):
                    continue
    return result


def build_status(db: Session, *, allowed_groups: list[str] | None = None) -> dict[str, Any]:
    state = ensure_system_state(db)
    settings_row = ensure_system_settings(db)
    api_online = False
    api_error: str | None = None
    try:
        live_nodes = oxidized_client_for(db).list_nodes()
        apply_live_nodes(db, live_nodes)
        api_online = True
        state.last_oxidized_seen_at = utcnow()
        db.commit()
    except AppError as exc:
        api_error = exc.code

    container: dict[str, Any] = {}
    docker_error: str | None = None
    try:
        container = docker_client_for(db).container_state()
    except AppError as exc:
        docker_error = exc.code
        container = {"status": "unavailable", "running": False, "restarting": False}

    nodes = list(db.scalars(select(Node)).all())
    if allowed_groups is not None:
        nodes = [node for node in nodes if node.group_name in allowed_groups]
        allowed_ids = {node.id for node in nodes}
    else:
        allowed_ids = None
    caches = {cache.node_id: cache for cache in db.scalars(select(NodeStatusCache)).all()}
    if allowed_ids is not None:
        caches = {key: value for key, value in caches.items() if key in allowed_ids}
    active_jobs = list(
        db.scalars(select(Job).where(Job.status.in_(("queued", "running"))).order_by(Job.id.desc())).all()
    )
    if allowed_ids is not None:
        active_jobs = [
            job
            for job in active_jobs
            if job.node_id in allowed_ids
            or any(
                int(value) in allowed_ids
                for value in (job.payload or {}).get("node_ids", [])
                if isinstance(value, (int, str)) and str(value).isdigit()
            )
        ]
    pending_ids = _active_job_node_ids(db, active_jobs)
    counts = {"total": len(nodes), "ok": 0, "failed": 0, "pending": 0, "never": 0}
    for node in nodes:
        if node.id in pending_ids:
            counts["pending"] += 1
            continue
        cache = caches.get(node.id)
        bucket = status_bucket(
            cache.status if cache else None,
            cache.last_success_at if cache else None,
            cache.last_failure_at if cache else None,
        )
        counts[bucket] += 1

    success_times = [ensure_utc(cache.last_success_at) for cache in caches.values() if cache.last_success_at]
    failure_times = [ensure_utc(cache.last_failure_at) for cache in caches.values() if cache.last_failure_at]
    success_times = [value for value in success_times if value is not None]
    failure_times = [value for value in failure_times if value is not None]

    running = bool(container.get("running"))
    restarting = bool(container.get("restarting"))
    if restarting:
        oxidized_state = "starting"
    elif running and api_online:
        oxidized_state = "online"
    elif running:
        oxidized_state = "degraded"
    elif docker_error:
        oxidized_state = "unknown" if api_online else "offline"
    else:
        oxidized_state = "offline"

    warnings: list[str] = []
    if not nodes:
        warnings.append("oxidized.no_nodes")
    if not api_online and nodes:
        warnings.append(api_error or "oxidized.unavailable")
    if docker_error:
        warnings.append(docker_error)
    config = applied_config(db)
    if not config.get("next_adds_job"):
        warnings.append("oxidized.next_adds_job_disabled")

    days = 14
    if settings_row.activity_retention_days:
        days = min(settings_row.activity_retention_days, 90)
    since = utcnow() - __import__("datetime").timedelta(days=days)
    groups: list[dict[str, Any]] = []
    group_query = (
        select(BackupRun.group_name, BackupRun.status, func.count(BackupRun.id))
        .where(BackupRun.finished_at.is_not(None), BackupRun.finished_at >= since)
        .group_by(BackupRun.group_name, BackupRun.status)
    )
    if allowed_groups is not None:
        group_query = group_query.where(BackupRun.group_name.in_(allowed_groups))
    for group_name, status, count in db.execute(group_query):
        groups.append({"group": group_name or "default", "status": status, "count": int(count)})
    sla_totals: dict[str, dict[str, int]] = {}
    for row in groups:
        bucket = sla_totals.setdefault(row["group"], {"success": 0, "failed": 0})
        if row["status"] == "success":
            bucket["success"] += row["count"]
        else:
            bucket["failed"] += row["count"]
    sla_groups = [
        {
            "group": name,
            "success": values["success"],
            "failed": values["failed"],
            "rate": (values["success"] / (values["success"] + values["failed"]))
            if values["success"] + values["failed"]
            else None,
        }
        for name, values in sorted(sla_totals.items())
    ]
    return {
        "oxidized": {
            "state": oxidized_state,
            "api_online": api_online,
            "container_state": container.get("status"),
            "container_running": running,
            "health": container.get("health"),
            "last_seen_at": to_iso(state.last_oxidized_seen_at),
            "version": None,
        },
        "nodes": counts,
        "backups": {
            "last_success_at": to_iso(max(success_times) if success_times else None),
            "last_failure_at": to_iso(max(failure_times) if failure_times else None),
            "active_jobs": len(active_jobs),
        },
        "activity": recent_activity(db, days=days, allowed_groups=allowed_groups),
        "sla": {"days": days, "groups": sla_groups},
        "warnings": list(dict.fromkeys(warnings)),
    }
