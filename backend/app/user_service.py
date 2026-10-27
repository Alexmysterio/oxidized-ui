from __future__ import annotations

from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .api_token_service import revoke_user_tokens
from .audit import add_audit
from .auth_service import revoke_user_sessions, validate_language
from .avatar_service import avatars_dir
from .errors import AppError
from .models import User
from .password_service import assert_not_reused, record_password, validate_new_password
from .schemas import UserCreate, UserPasswordReset, UserUpdate
from .scope_service import validate_scope_groups
from .security import (
    AuthContext,
    hash_password,
    normalize_username,
    validate_username,
)
from .serializers import user_public
from .timeutil import utcnow


def count_active_admins(db: Session) -> int:
    return db.scalar(select(func.count(User.id)).where(User.role == "admin", User.is_active.is_(True))) or 0


def get_user(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise AppError("user.not_found", params={"user_id": user_id})
    return user


def list_users(
    db: Session,
    *,
    search: str | None,
    role: str | None,
    is_active: bool | None,
    page: int,
    page_size: int,
) -> dict:
    query = select(User)
    if search:
        needle = f"%{search.strip()}%"
        query = query.where(
            User.username.ilike(needle) | User.full_name.ilike(needle) | User.email.ilike(needle)
        )
    if role:
        query = query.where(User.role == role)
    if is_active is not None:
        query = query.where(User.is_active.is_(is_active))
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(query.order_by(User.username).offset((page - 1) * page_size).limit(page_size)).all()
    return {
        "items": [user_public(user) for user in rows],
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": (total + page_size - 1) // page_size,
    }


def create_user(
    db: Session,
    *,
    payload: UserCreate,
    actor: AuthContext,
    request: Request,
) -> User:
    username = validate_username(payload.username)
    policy = validate_new_password(db, payload.password, username)
    language = validate_language(payload.language)
    user = User(
        username=username,
        username_key=normalize_username(username),
        password_hash=hash_password(payload.password),
        full_name=payload.full_name,
        email=payload.email,
        role=payload.role,
        language=language,
        theme="system",
        is_active=True,
        scope_groups=validate_scope_groups(db, payload.scope_groups),
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise AppError("user.duplicate_username", params={"username": username}) from exc
    db.refresh(user)
    record_password(db, user, user.password_hash, keep=policy.history_count)
    add_audit(
        db,
        actor=actor,
        action_code="user.created",
        action_params={"username": user.username, "role": user.role},
        target_type="user",
        target_id=user.id,
        request=request,
    )
    db.commit()
    return user


def update_user(
    db: Session,
    *,
    user_id: int,
    payload: UserUpdate,
    actor: AuthContext,
    request: Request,
) -> User:
    user = get_user(db, user_id)
    data = payload.model_dump(exclude_unset=True)
    changed = sorted(data)
    if user.role == "admin" and (data.get("role") not in (None, "admin") or data.get("is_active") is False):
        if count_active_admins(db) <= 1 and user.is_active:
            raise AppError("user.last_admin")
    if "language" in data and data["language"] is not None:
        user.language = validate_language(data["language"])
    if "full_name" in data:
        user.full_name = data["full_name"]
    if "email" in data:
        user.email = data["email"]
    if "role" in data and data["role"] is not None:
        user.role = data["role"]
    if "is_active" in data and data["is_active"] is not None:
        user.is_active = data["is_active"]
    if "scope_groups" in data:
        user.scope_groups = validate_scope_groups(db, data["scope_groups"])
    if user.id == actor.user_id and data.get("is_active") is False:
        raise AppError("user.self_delete")
    db.commit()
    db.refresh(user)
    if data.get("is_active") is False or "role" in data:
        revoke_user_sessions(db, user.id, except_session_id=actor.session_id if user.id == actor.user_id else None)
        revoke_user_tokens(db, user.id)
    add_audit(
        db,
        actor=actor,
        action_code="user.updated",
        action_params={"username": user.username, "changed_fields": changed},
        target_type="user",
        target_id=user.id,
        request=request,
    )
    db.commit()
    return user


def reset_password(
    db: Session,
    *,
    user_id: int,
    payload: UserPasswordReset,
    actor: AuthContext,
    request: Request,
) -> User:
    user = get_user(db, user_id)
    policy = validate_new_password(db, payload.new_password, user.username)
    assert_not_reused(db, user, payload.new_password, policy)
    user.password_hash = hash_password(payload.new_password)
    user.password_changed_at = utcnow()
    record_password(db, user, user.password_hash, keep=policy.history_count)
    db.commit()
    revoke_user_sessions(db, user.id, except_session_id=None)
    revoke_user_tokens(db, user.id)
    add_audit(
        db,
        actor=actor,
        action_code="user.password_reset",
        action_params={"username": user.username},
        target_type="user",
        target_id=user.id,
        request=request,
    )
    db.commit()
    return user


def delete_user(
    db: Session,
    *,
    user_id: int,
    actor: AuthContext,
    request: Request,
) -> None:
    user = get_user(db, user_id)
    if user.id == actor.user_id:
        raise AppError("user.self_delete")
    if user.role == "admin" and user.is_active and count_active_admins(db) <= 1:
        raise AppError("user.last_admin")
    username = user.username
    avatar = user.avatar_filename
    db.delete(user)
    db.commit()
    if avatar:
        try:
            (avatars_dir() / avatar).unlink(missing_ok=True)
        except OSError:
            pass
    add_audit(
        db,
        actor=actor,
        action_code="user.deleted",
        action_params={"username": username},
        target_type="user",
        target_id=user_id,
        request=request,
    )
    db.commit()
