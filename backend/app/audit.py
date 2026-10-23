from __future__ import annotations

from typing import Any

from fastapi import Request
from sqlalchemy.orm import Session

from .models import AuditLog
from .security import AuthContext, get_client_ip

SENSITIVE_KEY_FRAGMENTS = ("password", "secret", "token", "passphrase", "privatekey", "enable", "accesskey")


def _sanitize(value: Any, *, depth: int = 0) -> Any:
    if depth > 6:
        return "<too-deep>"
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if any(fragment in key_text.casefold() for fragment in SENSITIVE_KEY_FRAGMENTS):
                result[key_text] = "<redacted>"
            else:
                result[key_text] = _sanitize(item, depth=depth + 1)
        return result
    if isinstance(value, (list, tuple)):
        return [_sanitize(item, depth=depth + 1) for item in value[:100]]
    if isinstance(value, str):
        return value[:500]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)[:500]


def add_audit(
    db: Session,
    *,
    actor: AuthContext | None,
    action_code: str,
    action_params: dict[str, Any] | None = None,
    target_type: str | None = None,
    target_id: str | int | None = None,
    request: Request | None = None,
    actor_username: str | None = None,
    actor_role: str | None = None,
) -> AuditLog:
    if actor is not None:
        username = actor.username
        role = actor.role
        user_id: int | None = actor.user_id
    else:
        username = actor_username or "system"
        role = actor_role or "system"
        user_id = None
    entry = AuditLog(
        actor_user_id=user_id,
        actor_username=username,
        actor_role=role,
        action_code=action_code,
        action_params=_sanitize(action_params or {}),
        target_type=target_type,
        target_id=str(target_id) if target_id is not None else None,
        ip=get_client_ip(request) if request is not None else None,
        user_agent=(request.headers.get("user-agent") or "")[:512] if request is not None else None,
    )
    db.add(entry)
    return entry
