from __future__ import annotations

import logging
import re
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from .crypto import decrypt_json, encrypt_json
from .errors import AppError
from .models import Job, NotificationChannel
from .system_service import ensure_system_settings

logger = logging.getLogger("oxidized_ui.notifications")

KINDS = ("webhook", "slack", "discord", "telegram")
EVENTS = (
    "job.failed",
    "backup.stale",
    "config.changed",
    "backup.retry_exhausted",
    "system.health",
    "report.ready",
)
URL_RE = re.compile(r"^https?://\S+$")


def _text(value: Any, limit: int = 2048) -> str:
    return str(value or "").strip()[:limit]


def validate_config(kind: str, config: dict[str, Any]) -> dict[str, str]:
    if kind not in KINDS:
        raise AppError("validation.invalid_choice", params={"field": "kind"})
    if kind == "telegram":
        bot_token = _text(config.get("bot_token"), 512)
        chat_id = _text(config.get("chat_id"), 128)
        if not bot_token or not chat_id:
            raise AppError("validation.invalid_format", params={"field": "config"})
        return {"bot_token": bot_token, "chat_id": chat_id}
    key = "url" if kind == "webhook" else "webhook_url"
    url = _text(config.get(key), 2048)
    if not URL_RE.match(url):
        raise AppError("validation.invalid_format", params={"field": key})
    return {key: url}


def validate_events(events: list[str]) -> list[str]:
    cleaned = [event for event in dict.fromkeys(events) if event in EVENTS]
    if not cleaned:
        raise AppError("validation.invalid_format", params={"field": "events"})
    return cleaned


def channel_public(row: NotificationChannel) -> dict[str, Any]:
    try:
        config = decrypt_json(row.config_ciphertext, default={})
    except Exception:  # noqa: BLE001 - damaged config should not break the list
        config = {}
    return {
        "id": row.id,
        "name": row.name,
        "kind": row.kind,
        "enabled": row.enabled,
        "events": list(row.events or []),
        "digest_enabled": bool(row.digest_enabled),
        "config": config if isinstance(config, dict) else {},
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def ensure_legacy_channel(db: Session) -> None:
    settings_row = ensure_system_settings(db)
    legacy = (settings_row.notify_webhook_url or "").strip()
    if not legacy:
        return
    existing = db.scalar(select(NotificationChannel).where(NotificationChannel.name == "Legacy webhook"))
    if existing is None:
        db.add(
            NotificationChannel(
                name="Legacy webhook",
                kind="webhook",
                enabled=True,
                config_ciphertext=encrypt_json({"url": legacy}),
                events=list(EVENTS),
            )
        )
    settings_row.notify_webhook_url = ""
    db.commit()


def list_channels(db: Session) -> list[NotificationChannel]:
    ensure_legacy_channel(db)
    return list(db.scalars(select(NotificationChannel).order_by(NotificationChannel.id)).all())


def create_channel(db: Session, *, payload: Any) -> NotificationChannel:
    events = validate_events(payload.events)
    config = validate_config(payload.kind, payload.config)
    name = payload.name.strip()
    if not name:
        raise AppError("validation.invalid_format", params={"field": "name"})
    row = NotificationChannel(
        name=name,
        kind=payload.kind,
        enabled=bool(payload.enabled),
        config_ciphertext=encrypt_json(config),
        events=events,
        digest_enabled=bool(payload.digest_enabled),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update_channel(db: Session, channel_id: int, *, payload: Any) -> NotificationChannel:
    row = db.get(NotificationChannel, channel_id)
    if row is None:
        raise AppError("notification.not_found")
    if payload.name is not None:
        name = payload.name.strip()
        if not name:
            raise AppError("validation.invalid_format", params={"field": "name"})
        row.name = name
    if payload.kind is not None:
        row.kind = payload.kind
    if payload.enabled is not None:
        row.enabled = bool(payload.enabled)
    if payload.events is not None:
        row.events = validate_events(payload.events)
    if payload.digest_enabled is not None:
        row.digest_enabled = bool(payload.digest_enabled)
    if payload.config is not None:
        row.config_ciphertext = encrypt_json(validate_config(row.kind, payload.config))
    db.commit()
    db.refresh(row)
    return row


def delete_channel(db: Session, channel_id: int) -> None:
    row = db.get(NotificationChannel, channel_id)
    if row is None:
        raise AppError("notification.not_found")
    db.delete(row)
    db.commit()


def _send_channel(row: NotificationChannel, *, text: str, event: str) -> bool:
    try:
        config = decrypt_json(row.config_ciphertext, default={})
    except Exception:  # noqa: BLE001
        return False
    if not isinstance(config, dict):
        return False
    try:
        if row.kind == "webhook":
            response = httpx.post(
                str(config.get("url")),
                json={"text": text, "event": event, "source": "oxidized-ui"},
                timeout=httpx.Timeout(8, connect=4),
            )
        elif row.kind == "slack":
            response = httpx.post(
                str(config.get("webhook_url")),
                json={"text": text},
                timeout=httpx.Timeout(8, connect=4),
            )
        elif row.kind == "discord":
            response = httpx.post(
                str(config.get("webhook_url")),
                json={"content": text[:2000]},
                timeout=httpx.Timeout(8, connect=4),
            )
        elif row.kind == "telegram":
            token = str(config.get("bot_token") or "")
            response = httpx.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={
                    "chat_id": str(config.get("chat_id") or ""),
                    "text": text[:4096],
                    "disable_web_page_preview": True,
                },
                timeout=httpx.Timeout(8, connect=4),
            )
        else:
            return False
        response.raise_for_status()
        return True
    except Exception:  # noqa: BLE001 - notifications must never break jobs
        logger.warning("Notification failed for %s channel %s", row.kind, row.id)
        return False


def _legacy_send(db: Session, *, text: str, event: str) -> bool:
    row = ensure_system_settings(db)
    url = (row.notify_webhook_url or "").strip()
    if not url:
        return False
    try:
        response = httpx.post(
            url,
            json={"text": text, "event": event, "source": "oxidized-ui"},
            timeout=httpx.Timeout(8, connect=4),
        )
        response.raise_for_status()
        return True
    except Exception:  # noqa: BLE001
        logger.warning("Legacy webhook notification failed for %s", event)
        return False


def _notify(db: Session, *, text: str, event: str) -> dict[str, Any]:
    rows = list_channels(db)
    subscribed = [row for row in rows if row.enabled and event in (row.events or [])]
    if not rows:
        return {"ok": _legacy_send(db, text=text, event=event), "sent": 0, "failed": 0}
    results = [_send_channel(row, text=text, event=event) for row in subscribed]
    return {"ok": any(results), "sent": sum(results), "failed": len(results) - sum(results)}


def notify_job_failure(db: Session, job: Job) -> bool:
    row = ensure_system_settings(db)
    if not row.notify_on_failure:
        return False
    detail = job.error_code or "unknown"
    text = f"{row.site_name}: job #{job.id} ({job.kind}) failed: {detail}"
    return bool(_notify(db, text=text, event="job.failed")["ok"])


def notify_test(db: Session, channel_id: int | None = None) -> dict[str, Any]:
    row = ensure_system_settings(db)
    text = f"{row.site_name}: test notification"
    if channel_id is not None:
        channel = db.get(NotificationChannel, channel_id)
        if channel is None:
            raise AppError("notification.not_found")
        ok = _send_channel(channel, text=text, event="test")
        return {"ok": ok, "results": [{"id": channel.id, "name": channel.name, "ok": ok}]}
    rows = list_channels(db)
    if not rows:
        ok = _legacy_send(db, text=text, event="test")
        return {"ok": ok, "results": []}
    results = [
        {"id": channel.id, "name": channel.name, "ok": _send_channel(channel, text=text, event="test")}
        for channel in rows
        if channel.enabled
    ]
    return {"ok": any(result["ok"] for result in results), "results": results}


def notify_stale(db: Session, node_name: str, hours: int) -> bool:
    row = ensure_system_settings(db)
    text = f"{row.site_name}: node {node_name} has no successful backup for more than {hours} hours"
    return bool(_notify(db, text=text, event="backup.stale")["ok"])


def notify_config_change(db: Session, node_name: str, changed_at: Any) -> bool:
    row = ensure_system_settings(db)
    text = f"{row.site_name}: configuration changed on {node_name} ({changed_at})"
    return bool(_notify(db, text=text, event="config.changed")["ok"])


def notify_retry_exhausted(db: Session, node_name: str, attempts: int) -> bool:
    row = ensure_system_settings(db)
    text = f"{row.site_name}: giving up on {node_name} after {attempts} retries; check connectivity or credentials"
    return bool(_notify(db, text=text, event="backup.retry_exhausted")["ok"])


def notify_health(db: Session, warnings: list[str], percent: float, output_bytes: int) -> bool:
    row = ensure_system_settings(db)
    detail = ", ".join(warnings)
    text = (
        f"{row.site_name}: system health warning ({detail}); disk {percent}% used, "
        f"Oxidized data {round(output_bytes / (1024 * 1024), 1)} MB"
    )
    return bool(_notify(db, text=text, event="system.health")["ok"])


def notify_report_ready(db: Session, summary: str, uploaded: bool) -> bool:
    suffix = "uploaded to the export target" if uploaded else "stored locally"
    return bool(_notify(db, text=f"{summary} ({suffix})", event="report.ready")["ok"])


def _digest_text(db: Session, site_name: str, hours: int = 24) -> tuple[str, int]:
    from datetime import timedelta

    from sqlalchemy import func

    from .models import BackupRun, NodeConfigState
    from .models import Job as JobModel
    from .timeutil import utcnow

    cutoff = utcnow() - timedelta(hours=hours)
    failed_jobs = db.scalar(
        select(func.count(JobModel.id)).where(
            JobModel.status == "failed",
            JobModel.finished_at.is_not(None),
            JobModel.finished_at >= cutoff,
        )
    ) or 0
    failed_backups = db.scalar(
        select(func.count(BackupRun.id)).where(
            BackupRun.status != "success",
            BackupRun.finished_at.is_not(None),
            BackupRun.finished_at >= cutoff,
        )
    ) or 0
    changed = db.scalar(
        select(func.count(NodeConfigState.node_id)).where(NodeConfigState.last_changed_at >= cutoff)
    ) or 0
    total = int(failed_jobs) + int(failed_backups) + int(changed)
    text = (
        f"{site_name} daily digest ({hours} h): "
        f"{failed_jobs} failed jobs, {failed_backups} failed backups, {changed} configuration changes"
    )
    return text, total


def send_due_digests(db: Session) -> int:
    from datetime import timedelta
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

    from .timeutil import utcnow

    settings_row = ensure_system_settings(db)
    if not settings_row.digest_enabled:
        return 0
    now = utcnow()
    try:
        local_now = now.astimezone(ZoneInfo(settings_row.timezone)) if settings_row.timezone else now
    except (ZoneInfoNotFoundError, ValueError):
        local_now = now
    if local_now.hour != int(settings_row.digest_hour or 0):
        return 0
    text, total = _digest_text(db, settings_row.site_name)
    for channel in list_channels(db):
        if not channel.enabled or not channel.digest_enabled:
            continue
        last = channel.last_digest_at
        if last is not None and now - last < timedelta(hours=20):
            continue
        if _send_channel(channel, text=text, event="digest"):
            channel.last_digest_at = now
            db.commit()
    return total
