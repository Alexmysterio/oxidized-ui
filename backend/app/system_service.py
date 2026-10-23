from __future__ import annotations

import ipaddress
import re
import uuid
from datetime import UTC
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session

from .errors import AppError
from .models import SystemSettings, SystemState
from .settings import settings
from .timeutil import utcnow


def _normalize_allowlist(value: str) -> str:
    entries = [part.strip() for part in re.split(r"[\s,]+", value) if part.strip()]
    networks: list[str] = []
    for entry in entries:
        try:
            network = ipaddress.ip_network(entry, strict=False)
        except ValueError:
            raise AppError("system.invalid_setting", params={"key": "ip_allowlist"}) from None
        normalized = str(network)
        if normalized not in networks:
            networks.append(normalized)
    return "\n".join(networks)


def ensure_system_state(db: Session) -> SystemState:
    state = db.get(SystemState, 1)
    if state is None:
        state = SystemState(id=1, app_instance_id=str(uuid.uuid4()), initialized_at=utcnow())
        db.add(state)
        db.commit()
        db.refresh(state)
    return state


def ensure_system_settings(db: Session) -> SystemSettings:
    row = db.get(SystemSettings, 1)
    if row is None:
        row = SystemSettings(
            id=1,
            oxidized_api_url=settings.oxidized_api_url,
            oxidized_container_name=settings.oxidized_container_name,
            docker_proxy_url=settings.docker_proxy_url,
            timezone=None,
            activity_retention_days=0,
            audit_retention_days=180,
            poll_interval_seconds=settings.poll_interval_seconds,
            log_tail_default=500,
            config_backup_keep=settings.config_backup_keep,
            password_min_length=12,
            password_require_complexity=True,
            password_history_count=5,
            login_max_failures_per_user=settings.login_max_failures_per_user,
            login_max_failures_per_ip=settings.login_max_failures_per_ip,
            login_window_minutes=settings.login_window_minutes,
            login_lockout_minutes=30,
            ip_allowlist="",
            notify_webhook_url="",
            notify_on_failure=True,
            notify_stale_hours=0,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def get_settings_row(db: Session) -> SystemSettings:
    return ensure_system_settings(db)


def update_system_settings(db: Session, patch: dict) -> SystemSettings:
    row = ensure_system_settings(db)
    if "oxidized_api_url" in patch and patch["oxidized_api_url"] is not None:
        url = str(patch["oxidized_api_url"]).strip().rstrip("/")
        if not re.match(r"^https?://\S+$", url):
            raise AppError("system.invalid_setting", params={"key": "oxidized_api_url"})
        row.oxidized_api_url = url
    if "docker_proxy_url" in patch and patch["docker_proxy_url"] is not None:
        url = str(patch["docker_proxy_url"]).strip().rstrip("/")
        if not re.match(r"^https?://\S+$", url):
            raise AppError("system.invalid_setting", params={"key": "docker_proxy_url"})
        row.docker_proxy_url = url
    if "oxidized_container_name" in patch and patch["oxidized_container_name"] is not None:
        name = str(patch["oxidized_container_name"]).strip()
        if not re.match(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$", name):
            raise AppError("system.invalid_setting", params={"key": "oxidized_container_name"})
        row.oxidized_container_name = name
    if "timezone" in patch:
        timezone = patch["timezone"]
        if timezone in (None, ""):
            row.timezone = None
        else:
            try:
                ZoneInfo(str(timezone))
            except (ZoneInfoNotFoundError, ValueError):
                raise AppError("system.invalid_setting", params={"key": "timezone"}) from None
            row.timezone = str(timezone)
    for key in (
        "activity_retention_days",
        "audit_retention_days",
        "poll_interval_seconds",
        "log_tail_default",
        "config_backup_keep",
        "password_min_length",
        "password_history_count",
        "login_max_failures_per_user",
        "login_max_failures_per_ip",
        "login_window_minutes",
        "login_lockout_minutes",
    ):
        if key in patch and patch[key] is not None:
            setattr(row, key, int(patch[key]))
    if "password_require_complexity" in patch and patch["password_require_complexity"] is not None:
        row.password_require_complexity = bool(patch["password_require_complexity"])
    if "ip_allowlist" in patch and patch["ip_allowlist"] is not None:
        row.ip_allowlist = _normalize_allowlist(str(patch["ip_allowlist"]))
    if "notify_webhook_url" in patch and patch["notify_webhook_url"] is not None:
        row.notify_webhook_url = str(patch["notify_webhook_url"]).strip()[:2048]
    if "notify_on_failure" in patch and patch["notify_on_failure"] is not None:
        row.notify_on_failure = bool(patch["notify_on_failure"])
    if "notify_stale_hours" in patch and patch["notify_stale_hours"] is not None:
        row.notify_stale_hours = int(patch["notify_stale_hours"])
    row.updated_at = utcnow()
    db.commit()
    db.refresh(row)
    return row


def settings_public(row: SystemSettings) -> dict:
    return {
        "oxidized_api_url": row.oxidized_api_url,
        "oxidized_container_name": row.oxidized_container_name,
        "docker_proxy_url": row.docker_proxy_url,
        "timezone": row.timezone,
        "activity_retention_days": row.activity_retention_days,
        "audit_retention_days": row.audit_retention_days,
        "poll_interval_seconds": row.poll_interval_seconds,
        "log_tail_default": row.log_tail_default,
        "config_backup_keep": row.config_backup_keep,
        "password_min_length": row.password_min_length,
        "password_require_complexity": row.password_require_complexity,
        "password_history_count": row.password_history_count,
        "login_max_failures_per_user": row.login_max_failures_per_user,
        "login_max_failures_per_ip": row.login_max_failures_per_ip,
        "login_window_minutes": row.login_window_minutes,
        "login_lockout_minutes": row.login_lockout_minutes,
        "ip_allowlist": row.ip_allowlist,
        "notify_webhook_url": row.notify_webhook_url,
        "notify_on_failure": row.notify_on_failure,
        "notify_stale_hours": row.notify_stale_hours,
        "environment": {
            "oxidized_api_url": settings.oxidized_api_url,
            "oxidized_container_name": settings.oxidized_container_name,
            "docker_proxy_url": settings.docker_proxy_url,
        },
    }


def utc_zone_name() -> str:
    return str(UTC)
