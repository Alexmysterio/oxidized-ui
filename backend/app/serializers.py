from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from .crypto import decrypt_json
from .models import AuditLog, ConfigRevision, Job, Node, NodeStatusCache, User, UserSession
from .timeutil import to_iso


def user_public(user: User, *, include_state: bool = True) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": user.id,
        "username": user.username,
        "role": user.role,
        "language": user.language,
        "theme": user.theme,
    }
    if include_state:
        data.update(
            {
                "is_active": user.is_active,
                "created_at": to_iso(user.created_at),
                "updated_at": to_iso(user.updated_at),
                "last_login_at": to_iso(user.last_login_at),
                "password_changed_at": to_iso(user.password_changed_at),
            }
        )
    return data


def session_public(session: UserSession, *, current_id: int) -> dict[str, Any]:
    return {
        "id": session.id,
        "created_at": to_iso(session.created_at),
        "last_seen_at": to_iso(session.last_seen_at),
        "expires_at": to_iso(session.expires_at),
        "ip": session.ip,
        "user_agent": session.user_agent,
        "current": session.id == current_id,
    }


def node_vars(node: Node) -> dict[str, Any]:
    try:
        value = decrypt_json(node.vars_ciphertext, default={})
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def node_status_bucket(
    node: Node,
    cache: NodeStatusCache | None,
    *,
    active_job: Job | None = None,
) -> str:
    if active_job is not None and active_job.status in {"queued", "running"}:
        return "pending"
    if cache is None or cache.status is None:
        return "never"
    return "ok" if cache.status == "success" else "failed"


def node_public(
    db: Session,
    node: Node,
    *,
    role: str,
    cache: NodeStatusCache | None = None,
    active_job: Job | None = None,
) -> dict[str, Any]:
    cache = cache if cache is not None else db.get(NodeStatusCache, node.id)
    status = node_status_bucket(node, cache, active_job=active_job)
    data: dict[str, Any] = {
        "id": node.id,
        "name": node.name,
        "address": node.address,
        "model": node.model,
        "group_name": node.group_name,
        "status": status,
        "last_status_raw": cache.status if cache else None,
        "last_backup_at": to_iso(cache.last_success_at) if cache else None,
        "last_attempt_at": to_iso(cache.last_finished_at) if cache else None,
        "updated_at": to_iso(node.updated_at),
        "warnings": [],
    }
    if role in {"admin", "operator"}:
        data.update(
            {
                "input": node.input,
                "port": node.port,
                "username": node.username,
                "has_password": bool(node.password_ciphertext),
                "has_enable": bool(node.enable_ciphertext),
                "vars": node_vars(node),
                "output": node.output,
                "prompt": node.prompt,
                "timeout_seconds": node.timeout_seconds,
            }
        )
    elif role == "viewer":
        data.update(
            {
                "input": node.input,
                "port": node.port,
                "output": node.output,
                "prompt": node.prompt,
                "timeout_seconds": node.timeout_seconds,
            }
        )
    return data


def node_status_public(
    node: Node,
    cache: NodeStatusCache | None,
    *,
    active_job: Job | None = None,
    stale: bool = False,
) -> dict[str, Any]:
    data = {
        "node_id": node.id,
        "status": node_status_bucket(node, cache, active_job=active_job),
        "last_status_raw": cache.status if cache else None,
        "last_started_at": to_iso(cache.last_started_at) if cache else None,
        "last_finished_at": to_iso(cache.last_finished_at) if cache else None,
        "last_success_at": to_iso(cache.last_success_at) if cache else None,
        "last_failure_at": to_iso(cache.last_failure_at) if cache else None,
        "observed_at": to_iso(cache.observed_at) if cache else None,
        "active_job_id": active_job.id if active_job else None,
        "stale": stale,
    }
    if stale:
        data["warnings"] = ["oxidized.unavailable"]
    return data


def audit_public(entry: AuditLog) -> dict[str, Any]:
    return {
        "id": entry.id,
        "actor": {
            "user_id": entry.actor_user_id,
            "username": entry.actor_username,
            "role": entry.actor_role,
        },
        "action_code": entry.action_code,
        "action_params": entry.action_params or {},
        "target_type": entry.target_type,
        "target_id": entry.target_id,
        "ip": entry.ip,
        "created_at": to_iso(entry.created_at),
    }


def revision_public(revision: ConfigRevision) -> dict[str, Any]:
    return {
        "id": revision.id,
        "parent_id": revision.parent_id,
        "status": revision.status,
        "origin": revision.origin,
        "note": revision.note,
        "created_by_id": revision.created_by_id,
        "created_at": to_iso(revision.created_at),
        "applied_by_id": revision.applied_by_id,
        "applied_at": to_iso(revision.applied_at),
        "file_written_at": to_iso(revision.file_written_at),
        "config_sha256": revision.config_sha256,
        "yaml_sha256": revision.yaml_sha256,
    }
