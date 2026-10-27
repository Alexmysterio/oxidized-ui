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
            site_name="Oxidized UI",
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
        "retry_max_attempts",
        "retry_base_minutes",
        "digest_hour",
        "export_interval_hours",
        "backup_batch_size",
        "backup_batch_delay_seconds",
        "health_disk_warn_percent",
        "health_output_warn_mb",
        "health_alert_checks",
        "report_weekday",
        "report_hour",
        "report_keep",
        "smtp_port",
    ):
        if key in patch and patch[key] is not None:
            setattr(row, key, int(patch[key]))
    for key in (
        "password_require_complexity",
        "retry_failed_enabled",
        "digest_enabled",
        "export_enabled",
        "health_alerts_enabled",
        "report_enabled",
        "smtp_tls",
        "smtp_ssl",
    ):
        if key in patch and patch[key] is not None:
            setattr(row, key, bool(patch[key]))
    if "smtp_host" in patch and patch["smtp_host"] is not None:
        row.smtp_host = str(patch["smtp_host"]).strip()[:255]
    if "smtp_user" in patch and patch["smtp_user"] is not None:
        row.smtp_user = str(patch["smtp_user"]).strip()[:255]
    if "smtp_from" in patch and patch["smtp_from"] is not None:
        row.smtp_from = str(patch["smtp_from"]).strip()[:255]
    if "report_email_to" in patch and patch["report_email_to"] is not None:
        row.report_email_to = str(patch["report_email_to"]).strip()[:500]
    if patch.get("clear_smtp_password"):
        row.smtp_password_ciphertext = None
    elif patch.get("smtp_password"):
        from .crypto import encrypt_optional

        row.smtp_password_ciphertext = encrypt_optional(str(patch["smtp_password"]))
    if "ip_allowlist" in patch and patch["ip_allowlist"] is not None:
        row.ip_allowlist = _normalize_allowlist(str(patch["ip_allowlist"]))
    if "notify_webhook_url" in patch and patch["notify_webhook_url"] is not None:
        row.notify_webhook_url = str(patch["notify_webhook_url"]).strip()[:2048]
    if "notify_on_failure" in patch and patch["notify_on_failure"] is not None:
        row.notify_on_failure = bool(patch["notify_on_failure"])
    if "notify_stale_hours" in patch and patch["notify_stale_hours"] is not None:
        row.notify_stale_hours = int(patch["notify_stale_hours"])
    if "site_name" in patch and patch["site_name"] is not None:
        site_name = str(patch["site_name"]).strip()
        row.site_name = site_name[:100] or "Oxidized UI"
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
        "retry_failed_enabled": row.retry_failed_enabled,
        "retry_max_attempts": row.retry_max_attempts,
        "retry_base_minutes": row.retry_base_minutes,
        "digest_enabled": row.digest_enabled,
        "digest_hour": row.digest_hour,
        "backup_batch_size": row.backup_batch_size,
        "backup_batch_delay_seconds": row.backup_batch_delay_seconds,
        "health_alerts_enabled": row.health_alerts_enabled,
        "health_disk_warn_percent": row.health_disk_warn_percent,
        "health_output_warn_mb": row.health_output_warn_mb,
        "report_enabled": row.report_enabled,
        "report_weekday": row.report_weekday,
        "report_hour": row.report_hour,
        "report_keep": row.report_keep,
        "report_email_to": row.report_email_to,
        "health_alert_checks": row.health_alert_checks,
        "smtp_host": row.smtp_host,
        "smtp_port": row.smtp_port,
        "smtp_user": row.smtp_user,
        "smtp_from": row.smtp_from,
        "smtp_tls": row.smtp_tls,
        "smtp_ssl": row.smtp_ssl,
        "has_smtp_password": bool(row.smtp_password_ciphertext),
        "report_last_run_at": row.report_last_run_at.isoformat() if row.report_last_run_at else None,
        "site_name": row.site_name,
        "has_logo": bool(row.logo_filename),
        "environment": {
            "oxidized_api_url": settings.oxidized_api_url,
            "oxidized_container_name": settings.oxidized_container_name,
            "docker_proxy_url": settings.docker_proxy_url,
        },
    }


def utc_zone_name() -> str:
    return str(UTC)
