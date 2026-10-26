from __future__ import annotations

from collections import Counter

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import AuditLog, BackupRun, Job, Node, NodeStatusCache
from .oxidized import client_for as oxidized_client_for
from .serializers import status_bucket


def _metric(name: str, value: float | int, labels: dict[str, str] | None = None) -> str:
    suffix = ""
    if labels:
        encoded = ",".join(f'{key}="{str(val).replace(chr(34), chr(92) + chr(34))}"' for key, val in labels.items())
        suffix = "{" + encoded + "}"
    return f"{name}{suffix} {value}"


def render_metrics(db: Session) -> str:
    lines: list[str] = []
    lines.append("# HELP oxidized_ui_backups_total Backup runs by final status")
    lines.append("# TYPE oxidized_ui_backups_total counter")
    for status, count in db.execute(select(BackupRun.status, func.count(BackupRun.id)).group_by(BackupRun.status)):
        lines.append(_metric("oxidized_ui_backups_total", count, {"status": status}))
    total_duration = db.scalar(select(func.coalesce(func.sum(BackupRun.duration_seconds), 0)))
    count_duration = db.scalar(select(func.count(BackupRun.id)).where(BackupRun.duration_seconds.is_not(None)))
    lines.append("# HELP oxidized_ui_backup_duration_seconds_sum Total observed backup duration")
    lines.append("# TYPE oxidized_ui_backup_duration_seconds_sum counter")
    lines.append(_metric("oxidized_ui_backup_duration_seconds_sum", total_duration or 0))
    lines.append("# HELP oxidized_ui_backup_duration_seconds_count Number of observed backup durations")
    lines.append("# TYPE oxidized_ui_backup_duration_seconds_count counter")
    lines.append(_metric("oxidized_ui_backup_duration_seconds_count", count_duration or 0))

    from datetime import UTC, datetime, timedelta

    day_cutoff = datetime.now(UTC) - timedelta(hours=24)
    lines.append("# HELP oxidized_ui_backups_24h Backup runs finished in the last 24 hours")
    lines.append("# TYPE oxidized_ui_backups_24h gauge")
    for status, count in db.execute(
        select(BackupRun.status, func.count(BackupRun.id))
        .where(BackupRun.finished_at.is_not(None), BackupRun.finished_at >= day_cutoff)
        .group_by(BackupRun.status)
    ):
        lines.append(_metric("oxidized_ui_backups_24h", count, {"status": status}))
    lines.append("# HELP oxidized_ui_backup_success_ratio_24h Successful backups divided by finished backups in 24h")
    lines.append("# TYPE oxidized_ui_backup_success_ratio_24h gauge")
    counts = {
        status: count
        for status, count in db.execute(
            select(BackupRun.status, func.count(BackupRun.id))
            .where(BackupRun.finished_at.is_not(None), BackupRun.finished_at >= day_cutoff)
            .group_by(BackupRun.status)
        )
    }
    total = sum(counts.values())
    ratio = (counts.get("success", 0) / total) if total else 1.0
    lines.append(_metric("oxidized_ui_backup_success_ratio_24h", round(ratio, 4)))
    rows = db.execute(
        select(
            Node.name,
            NodeStatusCache.status,
            NodeStatusCache.last_success_at,
            NodeStatusCache.last_failure_at,
        ).join(NodeStatusCache, NodeStatusCache.node_id == Node.id, isouter=True)
    ).all()
    node_buckets = [
        (name, status_bucket(status, last_success, last_failure), last_success)
        for name, status, last_success, last_failure in rows
    ]
    lines.append("# HELP oxidized_ui_nodes_total Nodes by current status")
    lines.append("# TYPE oxidized_ui_nodes_total gauge")
    for status, count in sorted(Counter(bucket for _name, bucket, _last_success in node_buckets).items()):
        lines.append(_metric("oxidized_ui_nodes_total", count, {"status": status}))
    lines.append("# HELP oxidized_ui_jobs_active Jobs queued or running")
    lines.append("# TYPE oxidized_ui_jobs_active gauge")
    for status, count in db.execute(
        select(Job.status, func.count(Job.id)).where(Job.status.in_(("queued", "running"))).group_by(Job.status)
    ):
        lines.append(_metric("oxidized_ui_jobs_active", count, {"status": status}))
    lines.append("# HELP oxidized_ui_jobs_total Jobs by final status")
    lines.append("# TYPE oxidized_ui_jobs_total counter")
    for status, count in db.execute(select(Job.status, func.count(Job.id)).group_by(Job.status)):
        lines.append(_metric("oxidized_ui_jobs_total", count, {"status": status}))
    lines.append("# HELP oxidized_ui_jobs_24h Jobs finished in the last 24 hours")
    lines.append("# TYPE oxidized_ui_jobs_24h gauge")
    for status, count in db.execute(
        select(Job.status, func.count(Job.id))
        .where(Job.finished_at.is_not(None), Job.finished_at >= day_cutoff)
        .group_by(Job.status)
    ):
        lines.append(_metric("oxidized_ui_jobs_24h", count, {"status": status}))
    lines.append("# HELP oxidized_ui_audit_entries_total Audit log entries")
    lines.append("# TYPE oxidized_ui_audit_entries_total gauge")
    lines.append(_metric("oxidized_ui_audit_entries_total", db.scalar(select(func.count(AuditLog.id))) or 0))

    lines.append("# HELP oxidized_ui_node_last_success_timestamp_seconds Unix timestamp of last successful backup")
    lines.append("# TYPE oxidized_ui_node_last_success_timestamp_seconds gauge")
    for name, _bucket, last_success in node_buckets:
        if last_success is not None:
            lines.append(
                _metric(
                    "oxidized_ui_node_last_success_timestamp_seconds",
                    int(last_success.timestamp()),
                    {"node": name},
                )
            )
    lines.append("# HELP oxidized_ui_nodes_stale_24h Nodes without a successful backup in 24 hours")
    lines.append("# TYPE oxidized_ui_nodes_stale_24h gauge")
    from datetime import UTC, datetime, timedelta

    cutoff = datetime.now(UTC) - timedelta(hours=24)
    stale = 0
    for _name, _bucket, last_success in node_buckets:
        if last_success is None or last_success < cutoff:
            stale += 1
    lines.append(_metric("oxidized_ui_nodes_stale_24h", stale))
    lines.append("# HELP oxidized_ui_node_status Current node status as a labelled gauge")
    lines.append("# TYPE oxidized_ui_node_status gauge")
    for name, bucket, _last_success in node_buckets:
        lines.append(_metric("oxidized_ui_node_status", 1, {"node": name, "status": bucket}))

    try:
        up = 1 if oxidized_client_for(db).online() else 0
    except Exception:  # noqa: BLE001 - metrics endpoint must not fail
        up = 0
    lines.append("# HELP oxidized_ui_oxidized_up Oxidized API reachable")
    lines.append("# TYPE oxidized_ui_oxidized_up gauge")
    lines.append(_metric("oxidized_ui_oxidized_up", up))
    return "\n".join(lines) + "\n"
