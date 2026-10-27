from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from .models import BackupRun, Job, Node
from .settings import settings
from .system_service import ensure_system_settings
from .timeutil import utcnow

logger = logging.getLogger("oxidized_ui.health")


def _dir_size(path: Path) -> int:
    if not path.exists():
        return 0
    total = 0
    try:
        for item in path.rglob("*"):
            if item.is_file() and ".git" not in item.parts:
                try:
                    total += item.stat().st_size
                except OSError:
                    continue
    except OSError:
        return total
    return total


def _db_size() -> int:
    base = settings.data_dir / "oxidized-ui.sqlite3"
    total = 0
    for suffix in ("", "-wal", "-shm"):
        candidate = Path(f"{base}{suffix}")
        if candidate.exists():
            try:
                total += candidate.stat().st_size
            except OSError:
                continue
    return total


def migration_version(db: Session) -> str | None:
    try:
        return db.scalar(text("select version_num from alembic_version"))
    except Exception:  # noqa: BLE001 - table may not exist before migrations
        return None


def snapshot(db: Session) -> dict[str, Any]:
    row = ensure_system_settings(db)
    usage = shutil.disk_usage(settings.data_dir)
    percent = round((usage.used / usage.total) * 100, 1) if usage.total else 0.0
    output_bytes = _dir_size(settings.oxidized_config_dir)
    db_bytes = _db_size()
    queued = db.scalar(select(func.count(Job.id)).where(Job.status == "queued")) or 0
    running = db.scalar(select(func.count(Job.id)).where(Job.status == "running")) or 0
    failed_jobs = db.scalar(
        select(func.count(Job.id)).where(
            Job.status == "failed",
            Job.finished_at.is_not(None),
            Job.finished_at >= utcnow().replace(hour=0, minute=0, second=0, microsecond=0),
        )
    ) or 0
    stale_cutoff = utcnow()
    from datetime import timedelta

    stale_cutoff = stale_cutoff - timedelta(hours=24)
    failed_backups = db.scalar(
        select(func.count(BackupRun.id)).where(
            BackupRun.status != "success",
            BackupRun.finished_at.is_not(None),
            BackupRun.finished_at >= stale_cutoff,
        )
    ) or 0
    nodes = db.scalar(select(func.count(Node.id))) or 0

    warnings: list[str] = []
    disk_warn = int(row.health_disk_warn_percent or 0)
    if disk_warn and percent >= disk_warn:
        warnings.append("health.disk")
    output_warn_mb = int(row.health_output_warn_mb or 0)
    if output_warn_mb and output_bytes >= output_warn_mb * 1024 * 1024:
        warnings.append("health.output")
    return {
        "disk": {
            "total_bytes": usage.total,
            "used_bytes": usage.used,
            "free_bytes": usage.free,
            "percent": percent,
            "warn_percent": disk_warn,
        },
        "database_bytes": db_bytes,
        "output_bytes": output_bytes,
        "output_warn_mb": output_warn_mb,
        "jobs": {"queued": queued, "running": running, "failed_today": failed_jobs},
        "backups": {"failed_24h": failed_backups, "nodes": nodes},
        "migration": migration_version(db),
        "warnings": warnings,
        "alerts_enabled": bool(row.health_alerts_enabled),
        "checked_at": utcnow().isoformat(),
    }
