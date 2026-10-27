from __future__ import annotations

import base64
import hashlib
import io
import logging
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .crypto import decrypt_json, encrypt_json
from .encrypted_export import create_export
from .errors import AppError
from .jobs import create_and_submit
from .models import Job, SystemSettings
from .settings import settings
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
                "host_key_fingerprint": _text(config.get("host_key_fingerprint"), 128),
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
                "host_key_fingerprint": config.get("host_key_fingerprint"),
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
    from .encrypted_export import verify

    verify(passphrase, payload)
    filename = f"oxidized-ui-{utcnow().strftime('%Y%m%d-%H%M%S')}.oxui"
    return filename, payload


def configured(db: Session) -> bool:
    row = ensure_system_settings(db)
    return bool(row.export_config_ciphertext)


def _target_config(db: Session) -> dict[str, Any]:
    row = ensure_system_settings(db)
    if not row.export_config_ciphertext:
        raise AppError("export.not_configured")
    config = decrypt_json(row.export_config_ciphertext, default={})
    if not isinstance(config, dict) or not config.get("kind"):
        raise AppError("export.not_configured")
    return config


def upload_bytes(db: Session, filename: str, payload: bytes, *, passphrase: str | None = None) -> str:
    config = _target_config(db)
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
        logger.warning("Export upload failed: %s", exc)
        raise AppError("export.failed") from exc
    return config["kind"]


def _load_private_key(value: str):
    import paramiko

    for key_type in (paramiko.RSAKey, paramiko.ECDSAKey, paramiko.Ed25519Key):
        try:
            return key_type.from_private_key(io.StringIO(value))
        except (paramiko.SSHException, ValueError):
            continue
    raise AppError("export.private_key_invalid")


def _key_fingerprint(key) -> str:  # noqa: ANN001
    digest = hashlib.sha256(key.asbytes()).digest()
    return "SHA256:" + base64.b64encode(digest).decode("ascii").rstrip("=")


def _known_host_key(host: str, port: int):  # noqa: ANN201
    import paramiko

    path = Path(settings.oxidized_config_dir) / ".ssh" / "known_hosts"
    if not path.is_file():
        return None
    known = paramiko.HostKeys(str(path))
    for name in (f"[{host}]:{port}", host):
        entry = known.lookup(name)
        if entry is not None:
            return entry
    return None


def _verify_sftp_host_key(transport, config: dict[str, Any]) -> None:  # noqa: ANN001
    key = transport.get_remote_server_key()
    expected = str(config.get("host_key_fingerprint") or "").strip()
    actual = _key_fingerprint(key)
    if expected:
        if not expected.startswith("SHA256:"):
            expected = f"SHA256:{expected}"
        if expected.rstrip("=") != actual:
            raise AppError("export.host_key_mismatch", params={"fingerprint": actual})
        return
    known = _known_host_key(str(config["host"]), int(config.get("port") or 22))
    if known is None:
        raise AppError("export.host_key_unknown", params={"fingerprint": actual})
    if known.asbytes() != key.asbytes():
        raise AppError("export.host_key_mismatch", params={"fingerprint": actual})


@contextmanager
def _sftp_session(config: dict[str, Any]):  # noqa: ANN201
    import paramiko

    transport = paramiko.Transport((config["host"], int(config.get("port") or 22)))
    try:
        transport.start_client(timeout=15)
        _verify_sftp_host_key(transport, config)
        if config.get("private_key"):
            transport.auth_publickey(str(config["username"]), _load_private_key(str(config["private_key"])))
        else:
            transport.auth_password(str(config["username"]), str(config.get("password") or ""))
        if not transport.is_authenticated():
            raise AppError("export.failed")
        sftp = paramiko.SFTPClient.from_transport(transport)
        try:
            yield sftp
        finally:
            sftp.close()
    finally:
        transport.close()


def _upload_sftp(config: dict[str, Any], filename: str, payload: bytes) -> None:
    with _sftp_session(config) as sftp:
        remote = f"/{str(config.get('remote_dir') or '/').strip('/')}/{filename}".replace("//", "/")
        with sftp.file(remote, "wb") as handle:
            handle.write(payload)


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
    config = _target_config(db)
    filename, payload = _bundle(str(config.get("passphrase") or ""))
    target = upload_bytes(db, filename, payload)
    return {"filename": filename, "bytes": len(payload), "target": target}


def verify_bundle(db: Session, passphrase: str | None = None, *, remote: bool = False) -> dict[str, Any]:
    from .encrypted_export import verify

    config = _target_config(db)
    secret = (passphrase or "").strip() or str(config.get("passphrase") or "")
    if len(secret) < 12:
        raise AppError("validation.min", params={"field": "passphrase", "min": 12})
    if remote:
        filename, payload = _download_latest_bundle(config)
        result = verify(secret, payload)
        return {**result, "target": config["kind"], "mode": "remote", "filename": filename}
    payload = create_export(secret)
    result = verify(secret, payload)
    return {**result, "target": config["kind"], "mode": "self-test"}


def _download_latest_bundle(config: dict[str, Any]) -> tuple[str, bytes]:
    max_bytes = 512 * 1024 * 1024
    if config["kind"] == "sftp":
        remote_dir = str(config.get("remote_dir") or "/").rstrip("/") or "/"
        with _sftp_session(config) as sftp:
            entries = [
                item
                for item in sftp.listdir_attr(remote_dir)
                if item.filename.startswith("oxidized-ui-") and item.filename.endswith(".oxui")
            ]
            if not entries:
                raise AppError("export.remote_not_found")
            latest = max(entries, key=lambda item: item.st_mtime or 0)
            if int(latest.st_size or 0) > max_bytes:
                raise AppError("export.remote_too_large")
            with sftp.open(f"{remote_dir}/{latest.filename}", "rb") as handle:
                return latest.filename, handle.read()
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
    key_prefix = f"{prefix}/oxidized-ui-" if prefix else "oxidized-ui-"
    response = client.list_objects_v2(Bucket=config["bucket"], Prefix=key_prefix)
    objects = [item for item in response.get("Contents", []) if str(item.get("Key", "")).endswith(".oxui")]
    if not objects:
        raise AppError("export.remote_not_found")
    latest = max(objects, key=lambda item: item.get("LastModified"))
    if int(latest.get("Size") or 0) > max_bytes:
        raise AppError("export.remote_too_large")
    body = client.get_object(Bucket=config["bucket"], Key=latest["Key"])["Body"].read()
    return str(latest["Key"]).rsplit("/", 1)[-1], body


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
