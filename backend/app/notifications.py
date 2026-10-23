from __future__ import annotations

import logging

import httpx
from sqlalchemy.orm import Session

from .models import Job, SystemSettings
from .system_service import ensure_system_settings

logger = logging.getLogger("oxidized_ui.notifications")


def _send(db: Session, *, text: str, event: str) -> bool:
    row: SystemSettings = ensure_system_settings(db)
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
    except Exception:  # noqa: BLE001 - notifications must never break jobs
        logger.warning("Webhook notification failed for %s", event)
        return False


def notify_job_failure(db: Session, job: Job) -> bool:
    row = ensure_system_settings(db)
    if not row.notify_on_failure:
        return False
    detail = job.error_code or "unknown"
    return _send(db, text=f"Oxidized UI: job #{job.id} ({job.kind}) failed: {detail}", event="job.failed")


def notify_test(db: Session) -> bool:
    return _send(db, text="Oxidized UI: test notification", event="test")


def notify_stale(db: Session, node_name: str, hours: int) -> bool:
    return _send(
        db,
        text=f"Oxidized UI: node {node_name} has no successful backup for more than {hours} hours",
        event="backup.stale",
    )
