from __future__ import annotations

import hashlib
import logging
import os
import shutil
import tempfile
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .audit import add_audit
from .catalog import catalog
from .catalog import models as catalog_models
from .config_model import (
    config_hash,
    default_config,
    editable_yaml,
    load_editable_yaml,
    mask_source_token,
    render_effective_config,
    validate_config,
    validate_nodes_use_known_groups,
)
from .crypto import decrypt_json, decrypt_text, encrypt_json, encrypt_text
from .docker_api import client_for as docker_client_for
from .errors import AppError
from .jobs import create_and_submit
from .models import (
    ConfigFileSnapshot,
    ConfigRevision,
    Job,
    Node,
    ScheduledConfigApply,
    SystemState,
    User,
)
from .oxidized import client_for as oxidized_client_for
from .serializers import revision_public
from .settings import settings
from .system_service import ensure_system_state, get_settings_row
from .timeutil import utcnow
from .yaml_codec import parse_config_yaml

logger = logging.getLogger("oxidized_ui.config")

_APPLY_LOCK = threading.Lock()


def current_state(db: Session) -> SystemState:
    return ensure_system_state(db)


def get_applied_revision(db: Session) -> ConfigRevision | None:
    state = current_state(db)
    if state.active_revision_id:
        revision = db.get(ConfigRevision, state.active_revision_id)
        if revision is not None:
            return revision
    return db.scalar(
        select(ConfigRevision).where(ConfigRevision.status == "applied").order_by(ConfigRevision.id.desc()).limit(1)
    )


def get_draft_revision(db: Session) -> ConfigRevision | None:
    return db.scalar(
        select(ConfigRevision).where(ConfigRevision.status == "draft").order_by(ConfigRevision.id.desc()).limit(1)
    )


def latest_revision(db: Session) -> ConfigRevision | None:
    return db.scalar(select(ConfigRevision).order_by(ConfigRevision.id.desc()).limit(1))


def revision_config(revision: ConfigRevision) -> dict[str, Any]:
    value = decrypt_json(revision.config_ciphertext, default={})
    if not isinstance(value, dict):
        raise AppError("app.internal_error")
    return value


def revision_yaml(revision: ConfigRevision) -> str:
    value = decrypt_text(revision.yaml_ciphertext)
    return value or ""


def applied_config(db: Session) -> dict[str, Any]:
    revision = get_applied_revision(db)
    return revision_config(revision) if revision else default_config()


def applied_groups(db: Session) -> dict[str, Any]:
    config = applied_config(db)
    groups = config.get("groups") or {}
    return groups if isinstance(groups, dict) else {}


def file_sha256(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except FileNotFoundError:
        return None
    except OSError:
        return None


def drift_state(db: Session) -> dict[str, Any]:
    state = current_state(db)
    expected = state.active_file_sha256
    observed = file_sha256(settings.config_file)
    detected = bool(state.drift_detected_at) or (bool(expected) and (observed != expected or observed is None))
    return {
        "detected": detected,
        "expected_sha256": expected,
        "observed_sha256": observed,
        "file_exists": settings.config_file.exists(),
        "detected_at": state.drift_detected_at.isoformat() if state.drift_detected_at else None,
    }


def _atomic_write_config(text: str) -> None:
    settings.oxidized_config_dir.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=".config-", suffix=".tmp", dir=settings.oxidized_config_dir)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.chmod(temp_path, 0o640)
        except OSError:
            pass
        last_error: OSError | None = None
        for attempt in range(6):
            try:
                os.replace(temp_path, settings.config_file)
                last_error = None
                break
            except PermissionError as exc:
                # Windows can briefly deny a rename while an antivirus/indexer
                # holds the target. Linux is atomic and normally never retries.
                last_error = exc
                time.sleep(0.05 * (attempt + 1))
        if last_error is not None:
            raise last_error
        try:
            dir_fd = os.open(settings.oxidized_config_dir, os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except (OSError, AttributeError):
            # Directory fsync is Unix-only; Windows does not support it.
            pass
    finally:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass


def _backup_file(revision_id: int, keep: int) -> None:
    if not settings.config_file.exists():
        return
    settings.backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    target = settings.backup_dir / f"config-{stamp}-r{revision_id}.yaml"
    shutil.copy2(settings.config_file, target)
    try:
        os.chmod(target, 0o600)
    except OSError:
        pass
    if keep <= 0:
        return
    backups = sorted(settings.backup_dir.glob("config-*.yaml"), key=lambda path: path.stat().st_mtime)
    for old in backups[: max(0, len(backups) - keep)]:
        try:
            old.unlink()
        except OSError:
            pass


def _snapshot_file(
    db: Session,
    *,
    reason: str,
    actor_id: int | None = None,
    revision_id: int | None = None,
    write_db: bool = True,
) -> ConfigFileSnapshot | None:
    try:
        raw = settings.config_file.read_bytes()
    except FileNotFoundError:
        return None
    except OSError:
        return None
    text = raw.decode("utf-8", errors="replace")
    digest = hashlib.sha256(raw).hexdigest()
    snapshot = ConfigFileSnapshot(
        revision_id=revision_id,
        reason=reason,
        yaml_ciphertext=encrypt_text(text),
        sha256=digest,
        captured_by_id=actor_id,
    )
    if write_db:
        db.add(snapshot)
        db.commit()
        db.refresh(snapshot)
    return snapshot


def create_revision(
    db: Session,
    *,
    config: dict[str, Any],
    yaml_text: str,
    status: str,
    origin: str,
    actor_id: int | None,
    note: str | None = None,
    parent_id: int | None = None,
) -> ConfigRevision:
    revision = ConfigRevision(
        parent_id=parent_id,
        status=status,
        origin=origin,
        config_ciphertext=encrypt_json(config),
        yaml_ciphertext=encrypt_text(yaml_text),
        config_sha256=config_hash(config),
        yaml_sha256=hashlib.sha256(yaml_text.encode("utf-8")).hexdigest(),
        note=note,
        created_by_id=actor_id,
    )
    db.add(revision)
    db.commit()
    db.refresh(revision)
    return revision


def _strip_managed_from_external(data: dict[str, Any]) -> dict[str, Any]:
    import copy

    config = copy.deepcopy(data)
    source = config.get("source")
    if isinstance(source, dict):
        source.pop("default", None)
        http = source.get("http")
        if isinstance(http, dict):
            for key in ("url", "headers", "map", "vars_map"):
                http.pop(key, None)
    extensions = config.get("extensions")
    if isinstance(extensions, dict):
        web = extensions.get("oxidized-web")
        if isinstance(web, dict):
            for key in ("load", "listen", "port", "url_prefix"):
                web.pop(key, None)
    for section in ("group_map", "model_map"):
        mapping = config.get(section)
        if isinstance(mapping, dict):
            entries = []
            for key, target in mapping.items():
                is_regex = isinstance(key, str) and key.startswith("__regexp__:")
                if is_regex:
                    key = key[len("__regexp__:") :]
                entries.append({"match": str(key), "target": str(target), "is_regex": is_regex})
            config[section] = entries
    prompt = config.get("prompt")
    if isinstance(prompt, dict) and set(prompt.keys()) == {"$rubyRegexp"}:
        config["prompt"] = prompt["$rubyRegexp"]
    return config


def bootstrap_configuration(db: Session) -> None:
    """Create the first revision/file or detect an existing manual config.

    A pre-existing config is never overwritten. If it parses, it is adopted as
    the applied revision so the UI can show and edit it; otherwise a snapshot is
    kept and configuration writes remain blocked until an admin resolves drift.
    """
    state = ensure_system_state(db)
    applied = get_applied_revision(db)
    existing = settings.config_file
    if applied is not None:
        if not existing.exists():
            _atomic_write_config(render_effective_config(revision_config(applied)))
            state.active_file_sha256 = file_sha256(existing)
            db.commit()
        return

    if existing.exists():
        _snapshot_file(db, reason="external_import")
        try:
            raw_text = existing.read_text(encoding="utf-8")
            parsed = parse_config_yaml(raw_text)
            canonical = validate_config(_strip_managed_from_external(parsed))
        except Exception as exc:  # noqa: BLE001 - external file may be arbitrary YAML
            logger.warning("Existing Oxidized config could not be adopted: %s", type(exc).__name__)
            state.drift_detected_at = utcnow()
            db.commit()
            return
        revision = create_revision(
            db,
            config=canonical,
            yaml_text=raw_text,
            status="applied",
            origin="external_import",
            actor_id=None,
            note="Adopted existing config",
        )
        revision.applied_at = utcnow()
        revision.file_written_at = utcnow()
        revision.file_written_sha256 = file_sha256(existing)
        state.active_revision_id = revision.id
        state.active_file_sha256 = revision.file_written_sha256
        state.drift_detected_at = None
        db.commit()
        add_audit(
            db,
            actor=None,
            actor_username="system",
            actor_role="system",
            action_code="config.external_imported",
            action_params={"revision_id": revision.id, "path": "config"},
            target_type="config",
            target_id=revision.id,
        )
        db.commit()
        return

    config = default_config()
    yaml_text = render_effective_config(config)
    revision = create_revision(
        db,
        config=config,
        yaml_text=yaml_text,
        status="applied",
        origin="bootstrap",
        actor_id=None,
        note="Initial generated configuration",
    )
    _atomic_write_config(yaml_text)
    digest = file_sha256(existing)
    revision.applied_at = utcnow()
    revision.file_written_at = utcnow()
    revision.file_written_sha256 = digest
    state.active_revision_id = revision.id
    state.active_file_sha256 = digest
    db.commit()
    add_audit(
        db,
        actor=None,
        actor_username="system",
        actor_role="system",
        action_code="config.bootstrap_written",
        action_params={"revision_id": revision.id},
        target_type="config",
        target_id=revision.id,
    )
    db.commit()


def _expected_ok(db: Session, expected_revision_id: int | None) -> None:
    if expected_revision_id is None:
        return
    current = get_draft_revision(db) or get_applied_revision(db)
    current_id = current.id if current else None
    if current_id != expected_revision_id:
        raise AppError("config.stale_draft", params={"expected": expected_revision_id, "current": current_id})


def _config_from_request(config: dict[str, Any] | None, yaml_text: str | None) -> dict[str, Any]:
    if yaml_text is not None:
        return load_editable_yaml(yaml_text)
    if config is None:
        raise AppError("config.validation_failed", params={"reason": "missing_config"})
    return validate_config(config)


def create_draft(
    db: Session,
    *,
    config: dict[str, Any] | None,
    yaml_text: str | None,
    expected_revision_id: int | None,
    origin: str,
    actor_id: int | None,
    note: str | None = None,
) -> ConfigRevision:
    _expected_ok(db, expected_revision_id)
    normalized = _config_from_request(config, yaml_text)
    applied = get_applied_revision(db)
    if applied is not None and normalized == revision_config(applied):
        raise AppError("config.no_changes")
    previous_draft = get_draft_revision(db)
    if previous_draft is not None:
        previous_draft.status = "discarded"
    full_yaml = render_effective_config(normalized)
    revision = create_revision(
        db,
        config=normalized,
        yaml_text=full_yaml,
        status="draft",
        origin=origin,
        actor_id=actor_id,
        note=note,
        parent_id=applied.id if applied else None,
    )
    return revision


def validate_payload(
    db: Session,
    *,
    config: dict[str, Any] | None,
    yaml_text: str | None,
) -> dict[str, Any]:
    normalized = _config_from_request(config, yaml_text)
    applied = get_applied_revision(db)
    if applied is not None:
        applied_config = validate_config(revision_config(applied))
        applied_yaml = render_effective_config(applied_config, preview=True)
    else:
        applied_yaml = ""
    preview = render_effective_config(normalized, preview=True)
    from .diffing import build_diff

    diff = build_diff(applied_yaml, preview)
    return {
        "config": normalized,
        "editable_yaml": editable_yaml(normalized),
        "effective_yaml_preview": preview,
        "diff": diff,
    }


def config_detail(db: Session) -> dict[str, Any]:
    applied = get_applied_revision(db)
    draft = get_draft_revision(db)
    base = draft or applied
    config = revision_config(base) if base else default_config()
    editable = editable_yaml(config)
    effective_preview = render_effective_config(config, preview=True)
    drift = drift_state(db)
    return {
        "applied": revision_public(applied) if applied else None,
        "draft": revision_public(draft) if draft else None,
        "config": config,
        "editable_yaml": editable,
        "effective_yaml_preview": mask_source_token(effective_preview),
        "managed_keys": catalog()["managed_keys"],
        "drift": drift,
        "requires_apply": draft is not None,
    }


def revision_detail(db: Session, revision: ConfigRevision) -> dict[str, Any]:
    config = revision_config(revision)
    return {
        **revision_public(revision),
        "config": config,
        "editable_yaml": editable_yaml(config),
        "effective_yaml_preview": mask_source_token(render_effective_config(config, preview=True)),
    }


def revisions_page(db: Session, page: int, page_size: int) -> dict[str, Any]:
    query = select(ConfigRevision)
    total = db.scalar(select(func.count(ConfigRevision.id))) or 0
    rows = db.scalars(query.order_by(ConfigRevision.id.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return {
        "items": [revision_public(row) for row in rows],
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": (total + page_size - 1) // page_size,
    }


def revision_diff(db: Session, revision: ConfigRevision, against_id: int | None) -> dict[str, Any]:
    from .diffing import build_diff

    target = revision_config(revision)
    if against_id:
        against = db.get(ConfigRevision, against_id)
        if against is None:
            raise AppError("config.revision_not_found", params={"revision_id": against_id})
    else:
        against = get_applied_revision(db)
    base = revision_config(against) if against else default_config()
    old_yaml = editable_yaml(base)
    new_yaml = editable_yaml(target)
    diff = build_diff(old_yaml, new_yaml)
    return {
        "from": against.id if against else None,
        "to": revision.id,
        **diff,
    }


def restore_revision(
    db: Session,
    revision: ConfigRevision,
    *,
    actor_id: int,
    note: str | None,
) -> ConfigRevision:
    config = revision_config(revision)
    applied = get_applied_revision(db)
    if applied is not None and config == revision_config(applied):
        raise AppError("config.no_changes")
    previous_draft = get_draft_revision(db)
    if previous_draft is not None:
        previous_draft.status = "discarded"
    full_yaml = render_effective_config(config)
    restored = create_revision(
        db,
        config=config,
        yaml_text=full_yaml,
        status="draft",
        origin="rollback",
        actor_id=actor_id,
        note=note,
        parent_id=applied.id if applied else None,
    )
    return restored


def groups_in_use(db: Session) -> set[str]:
    return {group for group in db.scalars(select(Node.group_name).where(Node.group_name.is_not(None))).all() if group}


HEALTH_TIMEOUT_SECONDS = 60.0
HEALTH_POLL_SECONDS = 1.0


def preflight_config(db: Session, config: dict[str, Any]) -> list[str]:
    """Cheap checks before touching the live file.

    Unknown models are fatal because Oxidized cannot load those nodes. A
    temporarily unreachable oxidized-web is returned as a warning so an admin
    can still repair a broken configuration.
    """
    known_models = set(catalog_models())
    missing = [
        node.name
        for node in db.scalars(select(Node)).all()
        if node.model not in known_models
    ]
    default_model = config.get("model")
    if isinstance(default_model, str) and default_model and default_model not in known_models:
        missing.append(f"default:{default_model}")
    if missing:
        raise AppError("config.preflight_failed", params={"reason": "unknown_model", "models": missing[:20]})
    try:
        oxidized_client_for(db).list_nodes()
    except AppError as exc:
        return [exc.code]
    return []


def wait_for_health(db: Session, expected_names: set[str]) -> None:
    deadline = time.monotonic() + HEALTH_TIMEOUT_SECONDS
    last_error: str | None = None
    while time.monotonic() < deadline:
        try:
            live = oxidized_client_for(db).list_nodes()
        except AppError as exc:
            last_error = exc.code
        else:
            names = {node.name for node in live}
            if expected_names <= names:
                return
            last_error = "nodes_missing"
        time.sleep(HEALTH_POLL_SECONDS)
    raise AppError(
        "config.health_check_failed",
        params={"reason": last_error or "timeout", "expected": len(expected_names)},
    )


def rollback_apply(
    db: Session,
    *,
    revision: ConfigRevision,
    old_applied: ConfigRevision | None,
    previous_yaml: str | None,
    reason: str,
    docker,
    actor_id: int | None,
    restart: bool = True,
) -> None:
    if previous_yaml is not None:
        _atomic_write_config(previous_yaml)
    revision.status = "rolled_back"
    state = ensure_system_state(db)
    if old_applied is not None:
        old_applied.status = "applied"
        state.active_revision_id = old_applied.id
        state.active_file_sha256 = file_sha256(settings.config_file)
    else:
        state.active_revision_id = None
        state.active_file_sha256 = file_sha256(settings.config_file)
    state.last_apply_error_code = reason
    db.commit()
    user = db.get(User, actor_id) if actor_id else None
    add_audit(
        db,
        actor=None,
        actor_username=user.username if user else "system",
        actor_role=user.role if user else "system",
        action_code="config.apply_failed",
        action_params={"revision_id": revision.id, "error": reason, "rolled_back": True},
        target_type="config",
        target_id=revision.id,
    )
    add_audit(
        db,
        actor=None,
        actor_username=user.username if user else "system",
        actor_role=user.role if user else "system",
        action_code="config.rolled_back",
        action_params={"revision_id": revision.id, "reason": reason},
        target_type="config",
        target_id=revision.id,
    )
    db.commit()
    if restart:
        try:
            docker.restart()
        except AppError as exc:
            raise AppError("config.rollback_failed", params={"reason": exc.code}) from exc


def serialize_schedule(row: ScheduledConfigApply, job: Job | None = None) -> dict[str, Any]:
    return {
        "id": row.id,
        "revision_id": row.revision_id,
        "run_at": row.run_at.isoformat() if row.run_at else None,
        "status": row.status,
        "job_id": row.job_id,
        "job_status": job.status if job else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
        "error_code": row.error_code,
    }


def schedule_apply(db: Session, *, revision_id: int, run_at: datetime, actor_id: int) -> ScheduledConfigApply:
    revision = db.get(ConfigRevision, revision_id)
    if revision is None:
        raise AppError("config.revision_not_found", params={"revision_id": revision_id})
    if revision.status != "draft":
        raise AppError("config.not_draft", params={"status": revision.status})
    if run_at.tzinfo is None:
        run_at = run_at.replace(tzinfo=UTC)
    else:
        run_at = run_at.astimezone(UTC)
    if run_at <= utcnow() + timedelta(seconds=30):
        raise AppError("config.schedule_invalid", params={"reason": "must_be_future"})
    existing = db.scalar(
        select(ScheduledConfigApply).where(
            ScheduledConfigApply.revision_id == revision_id,
            ScheduledConfigApply.status == "pending",
        )
    )
    if existing is not None:
        raise AppError("config.schedule_conflict", params={"schedule_id": existing.id})
    row = ScheduledConfigApply(revision_id=revision_id, run_at=run_at, created_by_id=actor_id)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def scheduled_applies(db: Session) -> list[dict[str, Any]]:
    rows = db.scalars(
        select(ScheduledConfigApply).order_by(ScheduledConfigApply.run_at.desc()).limit(50)
    ).all()
    result = []
    for row in rows:
        job = db.get(Job, row.job_id) if row.job_id else None
        if row.status == "running" and job is not None and job.status in {"succeeded", "failed", "cancelled"}:
            row.status = "applied" if job.status == "succeeded" else "failed"
            row.finished_at = job.finished_at or utcnow()
            row.error_code = job.error_code
            db.commit()
        result.append(serialize_schedule(row, job))
    return result


def cancel_schedule(db: Session, schedule_id: int) -> None:
    row = db.get(ScheduledConfigApply, schedule_id)
    if row is None:
        raise AppError("config.schedule_not_found")
    if row.status != "pending":
        raise AppError("config.schedule_conflict", params={"status": row.status})
    row.status = "cancelled"
    row.finished_at = utcnow()
    db.commit()


def run_due_scheduled(db: Session) -> int:
    due = db.scalars(
        select(ScheduledConfigApply).where(
            ScheduledConfigApply.status == "pending",
            ScheduledConfigApply.run_at <= utcnow(),
        )
    ).all()
    started = 0
    for row in due:
        row.status = "running"
        row.started_at = utcnow()
        db.commit()
        try:
            job = start_apply(db, revision_id=row.revision_id, restart=True, actor_id=row.created_by_id or 1)
        except AppError as exc:
            if exc.code == "config.apply_busy":
                row.status = "pending"
                row.run_at = utcnow() + timedelta(minutes=1)
                db.commit()
                continue
            row.status = "failed"
            row.error_code = exc.code
            row.finished_at = utcnow()
            db.commit()
            continue
        row.job_id = job.id
        db.commit()
        started += 1
    return started


def start_apply(
    db: Session,
    *,
    revision_id: int,
    restart: bool,
    actor_id: int,
) -> Job:
    if not restart:
        raise AppError("config.restart_required")
    revision = db.get(ConfigRevision, revision_id)
    if revision is None:
        raise AppError("config.revision_not_found", params={"revision_id": revision_id})
    if revision.status != "draft":
        raise AppError("config.not_draft", params={"status": revision.status})
    draft = get_draft_revision(db)
    if draft is None or draft.id != revision.id:
        raise AppError("config.not_draft")
    active_jobs = db.scalar(select(Job).where(Job.kind == "config_apply", Job.status.in_(("queued", "running"))))
    if active_jobs is not None:
        raise AppError("config.apply_busy")
    config = revision_config(revision)
    validate_nodes_use_known_groups(config, groups_in_use(db))
    job = create_and_submit(
        db,
        kind="config_apply",
        actor_id=actor_id,
        payload={"revision_id": revision.id},
        progress_total=3,
        runner=run_config_apply_job,
    )
    return job


def run_config_apply_job(db: Session, job: Job) -> dict[str, Any]:
    if not _APPLY_LOCK.acquire(blocking=False):
        raise AppError("config.apply_busy")
    revision_id = int(job.payload.get("revision_id", 0))
    try:
        revision = db.get(ConfigRevision, revision_id)
        if revision is None:
            raise AppError("config.revision_not_found", params={"revision_id": revision_id})
        if revision.status != "draft":
            raise AppError("config.not_draft", params={"status": revision.status})
        config = revision_config(revision)
        validate_nodes_use_known_groups(config, groups_in_use(db))
        expected_names = {node.name for node in db.scalars(select(Node)).all()}
        warnings = preflight_config(db, config)
        job.progress_done = 1
        db.commit()

        state = ensure_system_state(db)
        old_applied = get_applied_revision(db)
        previous_yaml: str | None = None
        try:
            previous_yaml = settings.config_file.read_text(encoding="utf-8")
        except FileNotFoundError:
            if old_applied is not None:
                previous_yaml = revision_yaml(old_applied)
        except OSError:
            previous_yaml = revision_yaml(old_applied) if old_applied is not None else None

        current_hash = file_sha256(settings.config_file)
        if state.active_file_sha256 and current_hash != state.active_file_sha256:
            _snapshot_file(
                db,
                reason="pre_apply",
                actor_id=job.created_by_id,
                revision_id=revision.id,
            )
            state.drift_detected_at = utcnow()
            db.commit()

        keep = get_settings_row(db).config_backup_keep or settings.config_backup_keep
        _backup_file(revision.id, keep)
        full_yaml = render_effective_config(config)
        _atomic_write_config(full_yaml)
        now = utcnow()
        if old_applied is not None and old_applied.id != revision.id:
            old_applied.status = "superseded"
        revision.status = "applied"
        revision.applied_by_id = job.created_by_id
        revision.applied_at = now
        revision.file_written_at = now
        revision.file_written_sha256 = file_sha256(settings.config_file)
        revision.yaml_ciphertext = encrypt_text(full_yaml)
        revision.yaml_sha256 = hashlib.sha256(full_yaml.encode("utf-8")).hexdigest()
        state.active_revision_id = revision.id
        state.active_file_sha256 = revision.file_written_sha256
        state.drift_detected_at = None
        state.last_apply_error_code = None
        db.commit()
        job.progress_done = 2
        db.commit()

        docker = docker_client_for(db)
        restarted = False
        try:
            docker.restart()
            restarted = True
            wait_for_health(db, expected_names)
        except AppError as exc:
            # Restore the exact previous file before returning control. If the
            # restart itself failed, avoid masking that error with a second
            # restart failure; the restored file will be loaded on next start.
            rollback_apply(
                db,
                revision=revision,
                old_applied=old_applied,
                previous_yaml=previous_yaml,
                reason=exc.code,
                docker=docker,
                actor_id=job.created_by_id,
                restart=restarted,
            )
            raise
        user = db.get(User, job.created_by_id) if job.created_by_id else None
        add_audit(
            db,
            actor=None,
            actor_username=user.username if user else "system",
            actor_role=user.role if user else "system",
            action_code="config.applied",
            action_params={
                "revision_id": revision.id,
                "restarted": True,
                "health_check": "passed",
                "warnings": warnings,
            },
            target_type="config",
            target_id=revision.id,
        )
        db.commit()
        job.progress_done = 3
        db.commit()
        return {"revision_id": revision.id, "restarted": True, "warnings": warnings, "health_check": "passed"}
    except Exception:
        db.rollback()
        raise
    finally:
        _APPLY_LOCK.release()


def groups_list(db: Session) -> dict[str, Any]:
    from .config_model import redact_group_for_api

    applied = applied_groups(db)
    draft = get_draft_revision(db)
    draft_groups = {}
    if draft is not None:
        draft_config = revision_config(draft)
        draft_groups = draft_config.get("groups") or {}
    if not isinstance(draft_groups, dict):
        draft_groups = {}
    counts = {
        group: count
        for group, count in db.execute(select(Node.group_name, func.count(Node.id)).group_by(Node.group_name)).all()
        if group
    }
    rows = []
    for name, group in sorted(applied.items()):
        public = redact_group_for_api(name, group)
        public.update(
            {
                "node_count": counts.get(name, 0),
                "state": "applied",
                "draft": name in draft_groups and draft_groups.get(name) != group,
            }
        )
        rows.append(public)
    pending_names = sorted(set(draft_groups) - set(applied))
    for name in pending_names:
        public = redact_group_for_api(name, draft_groups[name])
        public.update({"node_count": 0, "state": "draft", "draft": True})
        rows.append(public)
    return {
        "groups": rows,
        "draft_revision_id": draft.id if draft else None,
        "requires_admin_apply": bool(draft is not None),
    }


def groups_detail(db: Session, name: str) -> dict[str, Any]:
    from .config_model import redact_group_for_api

    draft = get_draft_revision(db)
    config = revision_config(draft) if draft else applied_config(db)
    group = (config.get("groups") or {}).get(name)
    if group is None:
        raise AppError("group.not_found", params={"name": name})
    public = redact_group_for_api(name, group)
    public.update(
        {
            "state": "draft" if draft else "applied",
            "requires_admin_apply": draft is not None,
        }
    )
    return public


def group_write_config(
    db: Session,
    *,
    name: str | None,
    patch: dict[str, Any],
    actor_id: int,
    origin: str = "groups",
    note: str | None = None,
    expected_revision_id: int | None = None,
) -> ConfigRevision:
    from .config_model import apply_group_patch

    _expected_ok(db, expected_revision_id)
    draft = get_draft_revision(db)
    applied = get_applied_revision(db)
    base_revision = draft or applied
    config = revision_config(base_revision) if base_revision else default_config()
    groups = config.get("groups")
    if not isinstance(groups, dict):
        groups = {}
    target_name = name
    creating = target_name is not None and target_name not in groups
    if creating:
        groups[target_name] = apply_group_patch({}, patch, is_create=True)
    else:
        if target_name not in groups:
            raise AppError("group.not_found", params={"name": target_name})
        groups[target_name] = apply_group_patch(groups[target_name], patch)
    config["groups"] = groups
    normalized = validate_config(config)
    if draft is not None:
        draft.status = "discarded"
    full_yaml = render_effective_config(normalized)
    revision = create_revision(
        db,
        config=normalized,
        yaml_text=full_yaml,
        status="draft",
        origin=origin,
        actor_id=actor_id,
        note=note,
        parent_id=applied.id if applied else None,
    )
    return revision


def group_delete_config(
    db: Session,
    *,
    name: str,
    actor_id: int,
    expected_revision_id: int | None = None,
) -> ConfigRevision:
    _expected_ok(db, expected_revision_id)
    draft = get_draft_revision(db)
    applied = get_applied_revision(db)
    base = draft or applied
    config = revision_config(base) if base else default_config()
    groups = config.get("groups") or {}
    if not isinstance(groups, dict) or name not in groups:
        raise AppError("group.not_found", params={"name": name})
    if name in groups_in_use(db):
        raise AppError("group.in_use", params={"name": name})
    groups.pop(name)
    config["groups"] = groups
    normalized = validate_config(config)
    if draft is not None:
        draft.status = "discarded"
    full_yaml = render_effective_config(normalized)
    return create_revision(
        db,
        config=normalized,
        yaml_text=full_yaml,
        status="draft",
        origin="groups",
        actor_id=actor_id,
        parent_id=applied.id if applied else None,
    )


def health_config_writable() -> bool:
    try:
        settings.oxidized_config_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            prefix=".health-",
            dir=settings.oxidized_config_dir,
            delete=True,
        ) as probe:
            probe.write("ok")
            probe.flush()
        return True
    except OSError:
        return False
