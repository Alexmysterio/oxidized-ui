from __future__ import annotations

import io
import logging
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .crypto import decrypt_json, encrypt_json
from .encrypted_export import create_export
from .errors import AppError
from .jobs import create_and_submit
from .models import Job, SystemSettings
from .system_service import ensure_system_settings
from .timeutil import utcnow

logger = logging.getLogger("oxidized_ui.export")

KINDS = ("sftp", "s3")
DEFAULT_TIMEOUT = 30


def _text(value: Any, limit: int = 512) -> str:
    return str(value or "").strip()[:limit]


def validate_config(kind: str, config: dict[str, Any]) -> dict[str, Any]:
    if kind not in KINDS:
        raise AppError("validation.invalid_choice", params={"field": "kind"})
    passphrase = _text(config.get("passphrase"), 512)
    if len(passphrase) < 12:
        raise AppError("validation.min", params={"field": "passphrase", "min": 12})
    cleaned: dict[str, Any] = {"kind": kind, "passphrase": passphrase}
    if kind == "sftp":
        host = _text(config.get("host"), 255)
        username = _text(config.get("username"), 128)
        if not host or not username:
            raise AppError("validation.invalid_format", params={"field": "host"})
        cleaned.update(
            {
                "host": host,
                "port": int(config.get("port") or 22),
                "username": username,
                "password": _text(config.get("password"), 512),
                "private_key": _text(config.get("private_key"), 16384),
                "remote_dir": _text(config.get("remote_dir"), 512) or "/",
            }
        )
        if not cleaned["password"] and not cleaned["private_key"]:
            raise AppError("validation.invalid_format", params={"field": "password"})
    else:
        bucket = _text(config.get("bucket"), 255)
        if not bucket:
            raise AppError("validation.required", params={"field": "bucket"})
        cleaned.update(
            {
                "endpoint_url": _text(config.get("endpoint_url"), 512),
                "region": _text(config.get("region"), 64) or "us-east-1",
                "bucket": bucket,
                "prefix": _text(config.get("prefix"), 512).strip("/"),
                "access_key": _text(config.get("access_key"), 128),
                "secret_key": _text(config.get("secret_key"), 512),
                "use_ssl": bool(config.get("use_ssl", True)),
            }
        )
        if not cleaned["access_key"] or not cleaned["secret_key"]:
            raise AppError("validation.invalid_format", params={"field": "access_key"})
    return cleaned


def configure(
    db: Session,
    *,
    kind: str,
    config: dict[str, Any],
    interval_hours: int,
    enabled: bool,
) -> SystemSettings:
    cleaned = validate_config(kind, config)
    if interval_hours < 1 or interval_hours > 720:
        raise AppError("validation.range", params={"field": "interval_hours", "min": 1, "max": 720})
    row = ensure_system_settings(db)
    row.export_config_ciphertext = encrypt_json(cleaned)
    row.export_interval_hours = interval_hours
    row.export_enabled = enabled
    if enabled:
        row.export_next_run_at = utcnow() + timedelta(hours=interval_hours)
    else:
        row.export_next_run_at = None
    db.commit()
    db.refresh(row)
    return row


def public_status(row: SystemSettings) -> dict[str, Any]:
    try:
        config = decrypt_json(row.export_config_ciphertext, default={})
    except Exception:  # noqa: BLE001 - damaged config should not break settings
        config = {}
    config = config if isinstance(config, dict) else {}
    kind = config.get("kind")
    target: dict[str, Any] = {"kind": kind}
    if kind == "sftp":
        target.update(
            {
                "host": config.get("host"),
                "port": config.get("port"),
                "username": config.get("username"),
                "remote_dir": config.get("remote_dir"),
                "has_secret": bool(config.get("password") or config.get("private_key")),
            }
        )
    elif kind == "s3":
        target.update(
            {
                "endpoint_url": config.get("endpoint_url"),
                "region": config.get("region"),
                "bucket": config.get("bucket"),
                "prefix": config.get("prefix"),
                "has_secret": bool(config.get("access_key")),
            }
        )
    return {
        "configured": bool(config),
        "target": target,
        "enabled": bool(row.export_enabled),
        "interval_hours": row.export_interval_hours,
        "next_run_at": row.export_next_run_at.isoformat() if row.export_next_run_at else None,
        "last_run_at": row.export_last_run_at.isoformat() if row.export_last_run_at else None,
        "last_status": row.export_last_status,
        "last_error": row.export_last_error,
    }


def _bundle(passphrase: str) -> tuple[str, bytes]:
    payload = create_export(passphrase)
    filename = f"oxidized-ui-{utcnow().strftime('%Y%m%d-%H%M%S')}.oxui"
    return filename, payload


def _upload_sftp(config: dict[str, Any], filename: str, payload: bytes) -> None:
    import paramiko

    transport = paramiko.Transport((config["host"], int(config.get("port") or 22)))
    try:
        if config.get("private_key"):
            key = paramiko.RSAKey.from_private_key(io.StringIO(config["private_key"]))
            transport.connect(username=config["username"], pkey=key)
        else:
            transport.connect(username=config["username"], password=config.get("password"))
        sftp = paramiko.SFTPClient.from_transport(transport)
        try:
            remote = f"/{str(config.get('remote_dir') or '/').strip('/')}/{filename}".replace("//", "/")
            with sftp.file(remote, "wb") as handle:
                handle.write(payload)
        finally:
            sftp.close()
    finally:
        transport.close()


def _upload_s3(config: dict[str, Any], filename: str, payload: bytes) -> None:
    import boto3

    client = boto3.client(
        "s3",
        endpoint_url=config.get("endpoint_url") or None,
        region_name=config.get("region") or "us-east-1",
        aws_access_key_id=config["access_key"],
        aws_secret_access_key=config["secret_key"],
        use_ssl=bool(config.get("use_ssl", True)),
    )
    prefix = str(config.get("prefix") or "").strip("/")
    key = f"{prefix}/{filename}" if prefix else filename
    client.put_object(Bucket=config["bucket"], Key=key, Body=payload)


def upload(db: Session) -> dict[str, Any]:
    row = ensure_system_settings(db)
    if not row.export_config_ciphertext:
        raise AppError("export.not_configured")
    config = decrypt_json(row.export_config_ciphertext, default={})
    if not isinstance(config, dict) or not config.get("kind"):
        raise AppError("export.not_configured")
    filename, payload = _bundle(str(config.get("passphrase") or ""))
    try:
        if config["kind"] == "sftp":
            _upload_sftp(config, filename, payload)
        elif config["kind"] == "s3":
            _upload_s3(config, filename, payload)
        else:
            raise AppError("export.not_configured")
    except AppError:
        raise
    except Exception as exc:  # noqa: BLE001 - surface a stable error code
        logger.warning("Scheduled export failed: %s", exc)
        raise AppError("export.failed") from exc
    return {"filename": filename, "bytes": len(payload), "target": config["kind"]}


def run_export_job(db: Session, job: Job) -> dict[str, Any]:
    row = ensure_system_settings(db)
    try:
        result = upload(db)
    except AppError as exc:
        row.export_last_run_at = utcnow()
        row.export_last_status = "failed"
        row.export_last_error = exc.code
        db.commit()
        raise
    row.export_last_run_at = utcnow()
    row.export_last_status = "succeeded"
    row.export_last_error = None
    db.commit()
    return result


def run_due_export(db: Session) -> int:
    row = ensure_system_settings(db)
    if not row.export_enabled or not row.export_config_ciphertext:
        return 0
    now = utcnow()
    if row.export_next_run_at is None:
        row.export_next_run_at = now
        db.commit()
    if row.export_next_run_at > now:
        return 0
    active = db.scalar(select(Job).where(Job.kind == "backup_export", Job.status.in_(("queued", "running"))))
    row.export_next_run_at = now + timedelta(hours=int(row.export_interval_hours or 24))
    if active is not None:
        db.commit()
        return 0
    create_and_submit(
        db,
        kind="backup_export",
        actor_id=None,
        payload={"scheduled": True},
        progress_total=1,
        runner=run_export_job,
    )
    db.commit()
    return 1


def export_now(db: Session, *, actor_id: int | None) -> Job:
    row = ensure_system_settings(db)
    if not row.export_config_ciphertext:
        raise AppError("export.not_configured")
    active = db.scalar(select(Job).where(Job.kind == "backup_export", Job.status.in_(("queued", "running"))))
    if active is not None:
        raise AppError("job.already_running", params={"job_id": active.id})
    return create_and_submit(
        db,
        kind="backup_export",
        actor_id=actor_id,
        payload={"scheduled": False},
        progress_total=1,
        runner=run_export_job,
    )
