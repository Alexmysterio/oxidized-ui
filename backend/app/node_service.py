from __future__ import annotations

import csv
import io
import json
import logging
from typing import Any

from fastapi import Request
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .audit import add_audit
from .catalog import models as model_catalog
from .config_service import applied_config, applied_groups, get_draft_revision
from .crypto import decrypt_optional, encrypt_json, encrypt_optional
from .docker_api import client_for as docker_client_for
from .errors import AppError
from .models import Job as JobModel
from .models import Node, NodeStatusCache
from .node_error_service import latest_error
from .oxidized import client_for as oxidized_client_for
from .schemas import NodeCreate, NodeUpdate, validate_group_name
from .security import AuthContext
from .serializers import node_public, node_status_bucket, node_status_public, node_vars
from .settings import settings
from .timeutil import ensure_utc, to_iso, utcnow

logger = logging.getLogger("oxidized_ui.nodes")

NODE_SORT_FIELDS = {"name", "address", "model", "group_name", "updated_at", "status", "last_backup_at"}
CSV_COLUMNS = [
    "name",
    "address",
    "model",
    "group",
    "input",
    "port",
    "username",
    "password",
    "enable",
    "vars",
    "output",
    "prompt",
    "timeout_seconds",
]


def _known_models() -> set[str]:
    return set(model_catalog())


def _validate_group_for_node(db: Session, group_name: str | None) -> str | None:
    if not group_name:
        return None
    applied = applied_groups(db)
    if group_name in applied:
        return group_name
    draft = get_draft_revision(db)
    if draft is not None:
        draft_groups = (revision_config_safe(draft) or {}).get("groups") or {}
        if group_name in draft_groups:
            raise AppError("node.group_not_applied", params={"group": group_name})
    raise AppError("node.group_not_found", params={"group": group_name})


def revision_config_safe(revision) -> dict[str, Any]:  # noqa: ANN001
    from .config_service import revision_config

    try:
        return revision_config(revision)
    except AppError:
        return {}


def _model_warning(model: str) -> list[str]:
    return [] if model in _known_models() else ["node.model_not_in_catalog"]


def _port_warning(db: Session, node: Node) -> list[str]:
    effective = node.input
    if node.port is None:
        return []
    if effective is None:
        config = applied_config(db)
        input_cfg = config.get("input") if isinstance(config, dict) else None
        effective = input_cfg.get("default") if isinstance(input_cfg, dict) else None
    parts = {part.strip() for part in (effective or "").split(",") if part.strip()}
    if parts and not ({"ssh", "scp", "telnet"} & parts):
        return ["node.port_ignored_for_input"]
    return []


def _active_jobs(db: Session) -> dict[int, JobModel]:
    rows = db.scalars(
        select(JobModel)
        .where(JobModel.status.in_(("queued", "running")), JobModel.node_id.is_not(None))
        .order_by(JobModel.id.desc())
    ).all()
    result: dict[int, JobModel] = {}
    for row in rows:
        if row.node_id is not None and row.node_id not in result:
            result[row.node_id] = row
    return result


def _all_active_jobs(db: Session) -> list[JobModel]:
    return db.scalars(select(JobModel).where(JobModel.status.in_(("queued", "running")))).all()


def serialize_node(db: Session, node: Node, *, role: str) -> dict[str, Any]:
    cache = db.get(NodeStatusCache, node.id)
    active = _active_jobs(db).get(node.id)
    data = node_public(db, node, role=role, cache=cache, active_job=active)
    warnings = _model_warning(node.model) + _port_warning(db, node)
    data["warnings"] = warnings
    return data


def list_nodes(
    db: Session,
    *,
    role: str,
    search: str | None = None,
    group_name: str | None = None,
    model: str | None = None,
    status_filter: str | None = None,
    sort: str = "name",
    order: str = "asc",
    page: int = 1,
    page_size: int = 25,
) -> dict[str, Any]:
    if sort not in NODE_SORT_FIELDS:
        sort = "name"
    if order not in {"asc", "desc"}:
        order = "asc"
    query = select(Node)
    if group_name:
        query = query.where(Node.group_name == group_name)
    if model:
        query = query.where(Node.model == model)
    if search:
        needle = f"%{search.strip()}%"
        query = query.where(
            Node.name.ilike(needle)
            | Node.address.ilike(needle)
            | Node.model.ilike(needle)
            | Node.username.ilike(needle)
        )
    rows = list(db.scalars(query).all())
    active_jobs = _active_jobs(db)
    cache_by_node = {cache.node_id: cache for cache in db.scalars(select(NodeStatusCache)).all()}
    for node in rows:
        node._status_bucket = node_status_bucket(  # type: ignore[attr-defined]
            node, cache_by_node.get(node.id), active_job=active_jobs.get(node.id)
        )
        cache = cache_by_node.get(node.id)
        node._last_backup = cache.last_success_at if cache else None  # type: ignore[attr-defined]
    if status_filter:
        rows = [node for node in rows if node._status_bucket == status_filter]  # type: ignore[attr-defined]

    if sort == "status":
        rows.sort(key=lambda node: node._status_bucket, reverse=order == "desc")  # type: ignore[attr-defined]
    elif sort == "last_backup_at":
        rows.sort(
            key=lambda node: ensure_utc(node._last_backup) or utcnow().replace(year=1970),  # type: ignore[attr-defined]
            reverse=order == "desc",
        )
    else:
        rows.sort(
            key=lambda node: (getattr(node, sort) is None, str(getattr(node, sort)).casefold()),
            reverse=order == "desc",
        )
    total = len(rows)
    start = (page - 1) * page_size
    page_rows = rows[start : start + page_size]
    return {
        "items": [serialize_node(db, node, role=role) for node in page_rows],
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": (total + page_size - 1) // page_size,
    }


def get_node(db: Session, node_id: int) -> Node:
    node = db.get(Node, node_id)
    if node is None:
        raise AppError("node.not_found", params={"node_id": node_id})
    return node


def get_node_by_name(db: Session, name: str) -> Node | None:
    return db.scalar(select(Node).where(Node.name_key == name.casefold()))


def _set_secret_from_payload(node: Node, data: dict[str, Any]) -> None:
    if data.get("clear_password"):
        node.password_ciphertext = None
    elif "password" in data and data["password"]:
        node.password_ciphertext = encrypt_optional(str(data["password"]))
    if data.get("clear_enable"):
        node.enable_ciphertext = None
    elif "enable" in data and data["enable"]:
        node.enable_ciphertext = encrypt_optional(str(data["enable"]))


def create_node(
    db: Session,
    *,
    payload: NodeCreate,
    actor: AuthContext,
    request: Request,
    previous_count: int,
) -> dict[str, Any]:
    data = payload.model_dump(exclude_unset=True)
    group_name = _validate_group_for_node(db, data.get("group_name"))
    node = Node(
        name=payload.name,
        name_key=payload.name.casefold(),
        address=payload.address,
        model=payload.model,
        group_name=group_name,
        input=payload.input,
        port=payload.port,
        username=payload.username,
        output=payload.output,
        prompt=payload.prompt,
        timeout_seconds=payload.timeout_seconds,
        vars_ciphertext=encrypt_json(payload.vars or {}),
        created_by_id=actor.user_id,
        updated_by_id=actor.user_id,
    )
    _set_secret_from_payload(node, data)
    db.add(node)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise AppError("node.duplicate_name", params={"name": payload.name}) from exc
    db.refresh(node)
    add_audit(
        db,
        actor=actor,
        action_code="node.created",
        action_params={"name": node.name, "model": node.model, "group": node.group_name},
        target_type="node",
        target_id=node.id,
        request=request,
    )
    db.commit()
    reload_status, warnings = reload_after_node_change(db, previous_count=previous_count)
    data = serialize_node(db, node, role=actor.role)
    return {"node": data, "reload_status": reload_status, "warnings": warnings + data["warnings"]}


def update_node(
    db: Session,
    *,
    node_id: int,
    payload: NodeUpdate,
    actor: AuthContext,
    request: Request,
) -> dict[str, Any]:
    node = get_node(db, node_id)
    data = payload.model_dump(exclude_unset=True)
    changed = sorted(key for key in data if key not in {"password", "enable", "clear_password", "clear_enable"})
    if "group_name" in data:
        data["group_name"] = _validate_group_for_node(db, data["group_name"])
    if "name" in data and data["name"] is not None:
        node.name = data["name"]
        node.name_key = data["name"].casefold()
    for field in ("address", "model", "group_name", "input", "port", "username", "output", "prompt", "timeout_seconds"):
        if field in data:
            setattr(node, field, data[field])
    if "vars" in data:
        node.vars_ciphertext = encrypt_json(data["vars"] or {})
    _set_secret_from_payload(node, data)
    node.updated_by_id = actor.user_id
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise AppError("node.duplicate_name", params={"name": node.name}) from exc
    db.refresh(node)
    add_audit(
        db,
        actor=actor,
        action_code="node.updated",
        action_params={"name": node.name, "changed_fields": changed},
        target_type="node",
        target_id=node.id,
        request=request,
    )
    db.commit()
    reload_status, warnings = reload_after_node_change(db, previous_count=1)
    data = serialize_node(db, node, role=actor.role)
    return {"node": data, "reload_status": reload_status, "warnings": warnings + data["warnings"]}


def delete_node(
    db: Session,
    *,
    node_id: int,
    actor: AuthContext,
    request: Request,
) -> dict[str, Any]:
    node = get_node(db, node_id)
    name = node.name
    previous_count = db.scalar(select(func.count(Node.id))) or 0
    db.delete(node)
    db.commit()
    add_audit(
        db,
        actor=actor,
        action_code="node.deleted",
        action_params={"name": name},
        target_type="node",
        target_id=node_id,
        request=request,
    )
    db.commit()
    reload_status, warnings = reload_after_node_change(db, previous_count=previous_count)
    return {"deleted": 1, "reload_status": reload_status, "warnings": warnings}


def reload_after_node_change(db: Session, *, previous_count: int) -> tuple[str, list[str]]:
    remaining_count = db.scalar(select(func.count(Node.id))) or 0
    if remaining_count == 0:
        # Oxidized exits when its source returns an empty inventory. Restart it
        # so the container entrypoint waits for a new first node instead of
        # entering runit's crash loop.
        try:
            docker_client_for(db).restart()
            add_audit(
                db,
                actor=None,
                actor_username="system",
                actor_role="system",
                action_code="oxidized.auto_recovered",
                action_params={"reason": "empty_inventory"},
            )
            db.commit()
            return "recovered", []
        except AppError as restart_exc:
            return "failed", ["oxidized.auto_recovery_failed", restart_exc.code]
    try:
        oxidized_client_for(db).reload()
        return "ok", []
    except AppError as exc:
        if previous_count == 0:
            try:
                docker_client_for(db).restart()
                add_audit(
                    db,
                    actor=None,
                    actor_username="system",
                    actor_role="system",
                    action_code="oxidized.auto_recovered",
                    action_params={"reason": "zero_nodes_before_change"},
                )
                db.commit()
                return "recovered", []
            except AppError as restart_exc:
                return "failed", ["oxidized.auto_recovery_failed", restart_exc.code]
        return "failed", [
            exc.code if exc.code in {"oxidized.unavailable", "oxidized.timeout"} else "oxidized.reload_failed"
        ]


def bulk_action(
    db: Session,
    *,
    action: str,
    ids: list[int],
    group_name: str | None,
    actor: AuthContext,
    request: Request,
    model: str | None = None,
    input: str | None = None,
    port: int | None = None,
    vars: dict[str, Any] | None = None,
) -> dict[str, Any]:
    nodes = list(db.scalars(select(Node).where(Node.id.in_(ids))).all())
    found = {node.id for node in nodes}
    failed = [
        {"id": node_id, "code": "node.not_found", "params": {"node_id": node_id}}
        for node_id in ids
        if node_id not in found
    ]
    if action == "backup":
        from .backup_service import create_backup_all_job

        job = create_backup_all_job(db, actor=actor, node_ids=[node.id for node in nodes], request=request)
        return {"job_id": job.id, "requested": len(nodes), "failed": failed}
    if action == "change_group":
        validated = _validate_group_for_node(db, group_name)
        for node in nodes:
            node.group_name = validated
            node.updated_by_id = actor.user_id
        db.commit()
        add_audit(
            db,
            actor=actor,
            action_code="node.bulk_updated",
            action_params={"count": len(nodes), "change": "group", "group": validated},
            target_type="node",
            request=request,
        )
        db.commit()
        reload_status, warnings = reload_after_node_change(db, previous_count=1)
        return {
            "updated": len(nodes),
            "failed": failed,
            "reload_status": reload_status,
            "warnings": warnings,
        }
    if action == "update":
        changed = False
        for node in nodes:
            if group_name is not None:
                node.group_name = _validate_group_for_node(db, group_name)
                changed = True
            if model is not None:
                node.model = model
                changed = True
            if input is not None:
                node.input = input
                changed = True
            if port is not None:
                node.port = port
                changed = True
            if vars is not None:
                merged = dict(node.vars or {})
                merged.update(vars)
                node.vars = merged
                changed = True
            if changed:
                node.updated_by_id = actor.user_id
        if not changed:
            raise AppError("validation.invalid_format", params={"field": "changes"})
        db.commit()
        add_audit(
            db,
            actor=actor,
            action_code="node.bulk_updated",
            action_params={"count": len(nodes), "change": "fields"},
            target_type="node",
            request=request,
        )
        db.commit()
        reload_status, warnings = reload_after_node_change(db, previous_count=1)
        return {"updated": len(nodes), "failed": failed, "reload_status": reload_status, "warnings": warnings}
    if action == "delete":
        for node in nodes:
            db.delete(node)
        db.commit()
        add_audit(
            db,
            actor=actor,
            action_code="node.bulk_updated",
            action_params={"count": len(nodes), "change": "delete"},
            target_type="node",
            request=request,
        )
        db.commit()
        reload_status, warnings = reload_after_node_change(db, previous_count=1)
        return {
            "deleted": len(nodes),
            "failed": failed,
            "reload_status": reload_status,
            "warnings": warnings,
        }
    raise AppError("validation.invalid_choice", params={"field": "action"})


def node_source_payload(db: Session) -> list[dict[str, Any]]:
    config = applied_config(db)
    default_input = ""
    input_cfg = config.get("input") if isinstance(config, dict) else None
    if isinstance(input_cfg, dict):
        default_input = str(input_cfg.get("default") or "")
    result: list[dict[str, Any]] = []
    for node in db.scalars(select(Node)).all():
        payload: dict[str, Any] = {
            "name": node.name,
            "model": node.model,
        }
        if node.address:
            payload["ip"] = node.address
        if node.group_name:
            payload["group"] = node.group_name
        if node.input:
            payload["input"] = node.input
        if node.username:
            payload["username"] = node.username
        password = decrypt_optional(node.password_ciphertext)
        if password:
            payload["password"] = password
        enable = decrypt_optional(node.enable_ciphertext)
        vars_ = node_vars(node)
        vars_ = dict(vars_) if isinstance(vars_, dict) else {}
        if enable:
            vars_["enable"] = enable
        effective_input = node.input or default_input
        parts = {part.strip() for part in effective_input.split(",") if part.strip()}
        if node.port is not None:
            if "ssh" in parts or "scp" in parts:
                vars_["ssh_port"] = node.port
            if "telnet" in parts:
                vars_["telnet_port"] = node.port
        if vars_:
            payload["vars"] = vars_
        if node.output:
            payload["output"] = node.output
        if node.prompt:
            payload["prompt"] = node.prompt
        if node.timeout_seconds is not None:
            payload["timeout"] = node.timeout_seconds
        result.append(payload)
    return result


def node_status(
    db: Session,
    node: Node,
    *,
    refresh: bool = False,
) -> dict[str, Any]:
    if refresh:
        try:
            live = oxidized_client_for(db).list_nodes()
            match = next((item for item in live if item.name == node.name), None)
            if match is not None:
                update_status_cache(db, node, match)
        except AppError:
            pass
    cache = db.get(NodeStatusCache, node.id)
    active = _active_jobs(db).get(node.id)
    stale = False
    if refresh and cache is None:
        stale = True
    result = node_status_public(node, cache, active_job=active, stale=stale)
    if result["status"] == "failed":
        try:
            result["last_error"] = latest_error(db, node)
        except AppError:
            result["last_error"] = None
    else:
        result["last_error"] = None
    return result


def update_status_cache(db: Session, node: Node, live) -> None:  # noqa: ANN001
    cache = db.get(NodeStatusCache, node.id)
    if cache is None:
        cache = NodeStatusCache(node_id=node.id, observed_at=utcnow())
        db.add(cache)
    previous_success = cache.last_success_at
    previous_failure = cache.last_failure_at
    if live.status is not None:
        cache.status = live.status
    if live.last_started is not None:
        cache.last_started_at = live.last_started
    if live.last_finished is not None:
        cache.last_finished_at = live.last_finished
    if live.last_time is not None:
        cache.duration_seconds = int(live.last_time)
    if live.mtime is not None:
        cache.oxidized_mtime = live.mtime
    cache.observed_at = utcnow()
    cache.raw_last_json = json.dumps(
        {
            "status": live.status,
            "start": to_iso(live.last_started),
            "end": to_iso(live.last_finished),
        },
        ensure_ascii=False,
    )
    if live.status == "success" and live.last_finished:
        cache.last_success_at = live.last_finished
    elif live.status and live.status != "success" and live.last_finished:
        cache.last_failure_at = live.last_finished
    if cache.last_success_at is None:
        cache.last_success_at = previous_success
    if cache.last_failure_at is None:
        cache.last_failure_at = previous_failure
    db.commit()


def _csv_cell(value: Any) -> str:
    text = "" if value is None else str(value)
    if text.startswith(("=", "+", "-", "@")):
        return "'" + text
    return text


def export_csv(db: Session) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for node in db.scalars(select(Node).order_by(Node.name)).all():
        writer.writerow(
            {
                "name": _csv_cell(node.name),
                "address": _csv_cell(node.address),
                "model": _csv_cell(node.model),
                "group": _csv_cell(node.group_name),
                "input": _csv_cell(node.input),
                "port": _csv_cell(node.port),
                "username": _csv_cell(node.username),
                "password": "",
                "enable": "",
                "vars": _csv_cell(json.dumps(node_vars(node), ensure_ascii=False, separators=(",", ":"))),
                "output": _csv_cell(node.output),
                "prompt": _csv_cell(node.prompt),
                "timeout_seconds": _csv_cell(node.timeout_seconds),
            }
        )
    return buffer.getvalue()


def _parse_import_row(row: dict[str, str], row_number: int) -> dict[str, Any]:
    def value(key: str) -> str | None:
        raw = row.get(key)
        if raw is None:
            return None
        raw = raw.strip()
        return raw or None

    group = value("group") or value("group_name")
    if group:
        validate_group_name(group)
    port_raw = value("port")
    port = None
    if port_raw:
        try:
            port = int(port_raw)
        except ValueError as exc:
            raise AppError("node.invalid_port") from exc
    timeout_raw = value("timeout_seconds")
    timeout = int(timeout_raw) if timeout_raw else None
    vars_raw = value("vars")
    vars_value: Any = None
    if vars_raw:
        try:
            vars_value = json.loads(vars_raw)
        except json.JSONDecodeError as exc:
            raise AppError("node.invalid_vars", params={"row": row_number}) from exc
        if not isinstance(vars_value, dict):
            raise AppError("node.invalid_vars", params={"row": row_number})
    payload = {
        "name": value("name"),
        "address": value("address"),
        "model": value("model"),
        "group_name": group,
        "input": value("input"),
        "port": port,
        "username": value("username"),
        "password": value("password"),
        "enable": value("enable"),
        "vars": vars_value,
        "output": value("output"),
        "prompt": value("prompt"),
        "timeout_seconds": timeout,
    }
    return payload


def import_csv(
    db: Session,
    *,
    content: bytes,
    mode: str,
    dry_run: bool,
    actor: AuthContext,
    request: Request,
) -> dict[str, Any]:
    if len(content) > settings.max_csv_bytes:
        raise AppError("node.import_too_large")
    if mode not in {"skip_existing", "update_existing"}:
        raise AppError("validation.invalid_choice", params={"field": "mode"})
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise AppError("node.import_invalid", params={"reason": "encoding"}) from exc
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise AppError("node.import_invalid", params={"reason": "header"})
    allowed = set(CSV_COLUMNS) | {"group_name"}
    unknown = [name for name in reader.fieldnames if name not in allowed]
    if unknown:
        raise AppError("node.import_invalid", params={"reason": "unknown_columns", "columns": unknown})
    errors: list[dict[str, Any]] = []
    created = 0
    updated = 0
    skipped = 0
    seen_names: set[str] = set()
    previous_count = db.scalar(select(func.count(Node.id))) or 0
    changed = False
    for row_number, row in enumerate(reader, start=2):
        if row_number - 1 > settings.max_csv_rows:
            raise AppError("node.import_too_large", params={"max_rows": settings.max_csv_rows})
        try:
            payload = _parse_import_row(row, row_number)
            if not payload["name"] or not payload["model"]:
                raise AppError("validation.required", params={"row": row_number})
            name_key = payload["name"].casefold()
            if name_key in seen_names:
                raise AppError("node.duplicate_name", params={"name": payload["name"], "row": row_number})
            seen_names.add(name_key)
            payload["group_name"] = _validate_group_for_node(db, payload["group_name"])
            existing = get_node_by_name(db, payload["name"])
            if existing is not None and mode == "skip_existing":
                skipped += 1
                continue
            if existing is not None:
                update_payload = {key: value for key, value in payload.items() if value is not None}
                update_payload["clear_password"] = False
                update_payload["clear_enable"] = False
                body = NodeUpdate(**update_payload)
                if not dry_run:
                    _apply_update_without_audit(db, existing, body, actor)
                    changed = True
                updated += 1
            else:
                body = NodeCreate(**{key: value for key, value in payload.items() if value is not None})
                if not dry_run:
                    node = Node(
                        name=body.name,
                        name_key=body.name.casefold(),
                        address=body.address,
                        model=body.model,
                        group_name=body.group_name,
                        input=body.input,
                        port=body.port,
                        username=body.username,
                        output=body.output,
                        prompt=body.prompt,
                        timeout_seconds=body.timeout_seconds,
                        vars_ciphertext=encrypt_json(body.vars or {}),
                        password_ciphertext=encrypt_optional(body.password),
                        enable_ciphertext=encrypt_optional(body.enable),
                        created_by_id=actor.user_id,
                        updated_by_id=actor.user_id,
                    )
                    db.add(node)
                    changed = True
                created += 1
        except ValidationError as exc:
            if len(errors) < 500:
                for item in exc.errors()[:10]:
                    errors.append(
                        {
                            "row": row_number,
                            "path": ".".join(str(part) for part in item.get("loc", [])),
                            "code": "validation.failed",
                            "params": {"type": item.get("type")},
                        }
                    )
        except AppError as exc:
            if len(errors) < 500:
                errors.append({"row": row_number, "code": exc.code, "params": exc.params})
        except (ValueError, TypeError) as exc:
            if len(errors) < 500:
                errors.append({"row": row_number, "code": "node.import_invalid", "params": {"reason": str(exc)[:120]}})
    if not dry_run:
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise AppError("node.duplicate_name") from exc
        if changed:
            add_audit(
                db,
                actor=actor,
                action_code="node.imported",
                action_params={"created": created, "updated": updated, "skipped": skipped},
                target_type="node",
                request=request,
            )
            db.commit()
            reload_status, warnings = reload_after_node_change(db, previous_count=previous_count)
        else:
            reload_status, warnings = "skipped", []
    else:
        reload_status, warnings = "skipped", []
    return {
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "errors": errors,
        "dry_run": dry_run,
        "reload_status": reload_status,
        "warnings": warnings,
    }


def _apply_update_without_audit(db: Session, node: Node, payload: NodeUpdate, actor: AuthContext) -> None:
    data = payload.model_dump(exclude_unset=True)
    if "group_name" in data:
        data["group_name"] = _validate_group_for_node(db, data["group_name"])
    if "name" in data and data["name"]:
        node.name = data["name"]
        node.name_key = data["name"].casefold()
    for field in ("address", "model", "group_name", "input", "port", "username", "output", "prompt", "timeout_seconds"):
        if field in data:
            setattr(node, field, data[field])
    if "vars" in data:
        node.vars_ciphertext = encrypt_json(data["vars"] or {})
    _set_secret_from_payload(node, data)
    node.updated_by_id = actor.user_id
