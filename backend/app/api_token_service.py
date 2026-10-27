from __future__ import annotations

import secrets
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .errors import AppError
from .models import ApiToken, User
from .security import AuthContext, hash_token, new_session_token
from .timeutil import to_iso, utcnow

ROLE_RANK = {"viewer": 1, "operator": 2, "admin": 3}


def _serialize(row: ApiToken) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "prefix": row.prefix,
        "role": row.role,
        "created_at": to_iso(row.created_at),
        "expires_at": to_iso(row.expires_at),
        "last_used_at": to_iso(row.last_used_at),
        "revoked": row.revoked_at is not None,
    }


def list_tokens(db: Session, user_id: int) -> list[dict[str, Any]]:
    rows = db.scalars(
        select(ApiToken).where(ApiToken.user_id == user_id).order_by(ApiToken.created_at.desc())
    ).all()
    return [_serialize(row) for row in rows]


def create_token(db: Session, user: User, *, name: str, role: str, days: int) -> tuple[str, dict[str, Any]]:
    name = name.strip()
    if not name or len(name) > 100:
        raise AppError("validation.invalid_format", params={"field": "name"})
    if ROLE_RANK.get(role, 0) > ROLE_RANK.get(user.role, 0):
        raise AppError("auth.forbidden")
    prefix = "oxui_" + secrets.token_hex(4)
    raw = f"{prefix}_{new_session_token()}"
    row = ApiToken(
        user_id=user.id,
        name=name,
        prefix=prefix,
        token_hash=hash_token(raw),
        role=role,
        expires_at=utcnow() + timedelta(days=max(1, min(int(days), 365))),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return raw, _serialize(row)


def revoke_token(db: Session, user_id: int, token_id: int) -> None:
    row = db.get(ApiToken, token_id)
    if row is None or row.user_id != user_id:
        raise AppError("auth.token_not_found")
    if row.revoked_at is None:
        row.revoked_at = utcnow()
        db.commit()


def authenticate_token(db: Session, raw: str) -> tuple[User, ApiToken]:
    row = db.scalar(select(ApiToken).where(ApiToken.token_hash == hash_token(raw)))
    if row is None or row.revoked_at is not None:
        raise AppError("auth.unauthenticated")
    if row.expires_at is not None and row.expires_at <= utcnow():
        raise AppError("auth.session_expired")
    user = db.get(User, row.user_id)
    if user is None or not user.is_active:
        raise AppError("auth.unauthenticated")
    row.last_used_at = utcnow()
    db.commit()
    return user, row


def revoke_user_tokens(db: Session, user_id: int) -> None:
    rows = db.scalars(select(ApiToken).where(ApiToken.user_id == user_id, ApiToken.revoked_at.is_(None))).all()
    now = utcnow()
    for row in rows:
        row.revoked_at = now
    db.commit()


def context_from_token(user: User, token: ApiToken, raw: str) -> AuthContext:
    role = token.role
    if ROLE_RANK.get(role, 0) > ROLE_RANK.get(user.role, 0):
        role = user.role
    return AuthContext(
        user_id=user.id,
        username=user.username,
        role=role,
        language=user.language,
        theme=user.theme,
        session_id=0,
        session_token=raw,
        csrf_token="",
        scope_groups=[str(group) for group in user.scope_groups] if user.scope_groups else None,
    )
