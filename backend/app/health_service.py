from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from .models import BackupRun, HealthSample, Job, Node
from .settings import settings
from .system_service import ensure_system_settings
from .timeutil import ensure_utc, to_iso, utcnow

logger = logging.getLogger("oxidized_ui.health")

_health_streaks: dict[str, int] = {}


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
        "alert_checks": int(row.health_alert_checks or 3),
        "checked_at": utcnow().isoformat(),
    }


def record_sample(db: Session, snapshot: dict[str, Any] | None = None) -> None:
    from datetime import timedelta

    data = snapshot or snapshot_for(db)
    now = utcnow()
    db.add(
        HealthSample(
            observed_at=now,
            disk_percent=float(data["disk"]["percent"]),
            db_bytes=int(data["database_bytes"]),
            output_bytes=int(data["output_bytes"]),
            queue_depth=int(data["jobs"]["queued"]) + int(data["jobs"]["running"]),
            nodes=int(data["backups"]["nodes"]),
        )
    )
    db.execute(HealthSample.__table__.delete().where(HealthSample.observed_at < now - timedelta(days=30)))
    db.commit()


def history(db: Session, *, hours: int = 168, allowed_groups: list[str] | None = None) -> dict[str, Any]:
    from datetime import timedelta

    cutoff = utcnow() - timedelta(hours=max(1, min(hours, 24 * 30)))
    rows = list(
        db.scalars(
            select(HealthSample)
            .where(HealthSample.observed_at >= cutoff)
            .order_by(HealthSample.observed_at)
            .limit(1000)
        ).all()
    )
    return {
        "samples": [
            {
                "observed_at": to_iso(row.observed_at),
                "disk_percent": row.disk_percent,
                "db_bytes": row.db_bytes,
                "output_bytes": row.output_bytes,
                "queue_depth": row.queue_depth,
                "nodes": row.nodes,
            }
            for row in rows
        ],
        "top_nodes": top_nodes(db, allowed_groups=allowed_groups),
    }


def top_nodes(
    db: Session, *, limit: int = 5, allowed_groups: list[str] | None = None
) -> list[dict[str, Any]]:
    nodes = list(db.scalars(select(Node)).all())
    if allowed_groups is not None:
        nodes = [node for node in nodes if node.group_name in allowed_groups]
    names = {node.name_key: node.name for node in nodes}
    sizes: dict[str, int] = {}
    base = settings.oxidized_config_dir
    if not base.exists() or not names:
        return []
    try:
        for item in base.rglob("*"):
            if not item.is_file() or ".git" in item.parts:
                continue
            parts = {part.casefold() for part in item.parts}
            for key, name in names.items():
                if key in parts or item.stem.casefold() == key:
                    try:
                        sizes[name] = sizes.get(name, 0) + item.stat().st_size
                    except OSError:
                        continue
                    break
    except OSError:
        pass
    return [
        {"name": name, "bytes": size}
        for name, size in sorted(sizes.items(), key=lambda pair: pair[1], reverse=True)[: max(1, limit)]
    ]


def snapshot_for(db: Session) -> dict[str, Any]:
    return snapshot(db)


def process_health(db: Session) -> dict[str, Any]:
    from .notifications import notify_health

    row = ensure_system_settings(db)
    data = snapshot(db)
    record_sample(db, data)
    required = max(1, min(int(row.health_alert_checks or 3), 24))
    due: list[str] = []
    for warning in ("health.disk", "health.output"):
        if warning in data["warnings"]:
            _health_streaks[warning] = _health_streaks.get(warning, 0) + 1
            if _health_streaks[warning] == required:
                due.append(warning)
        else:
            _health_streaks.pop(warning, None)
    if due and row.health_alerts_enabled:
        notify_health(db, due, float(data["disk"]["percent"]), int(data["output_bytes"]))
    return data


def latest_sample(db: Session) -> dict[str, Any] | None:
    row = db.scalar(select(HealthSample).order_by(HealthSample.observed_at.desc()).limit(1))
    if row is None:
        return None
    return {"observed_at": to_iso(ensure_utc(row.observed_at)), "disk_percent": row.disk_percent}
