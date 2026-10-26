from __future__ import annotations

import logging
import threading
from datetime import timedelta
from typing import Any

from fastapi import Request
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .audit import add_audit
from .errors import AppError
from .mfa_service import create_challenge
from .mfa_service import is_enabled as mfa_is_enabled
from .models import User, UserSession
from .password_service import assert_not_reused, record_password, validate_new_password
from .rate_limit import check_login_allowed, clear_failures, record_attempt
from .security import (
    AuthContext,
    csrf_token_for,
    dummy_verify,
    get_client_ip,
    hash_password,
    hash_token,
    new_session_token,
    normalize_username,
    session_expiry,
    validate_username,
    verify_password,
)
from .settings import settings
from .system_service import ensure_system_state
from .timeutil import utcnow

logger = logging.getLogger("oxidized_ui.auth")
_SETUP_LOCK = threading.Lock()


def validate_language(language: str) -> str:
    languages = settings.available_languages
    if language not in languages:
        raise AppError("setup.invalid_language", params={"language": language})
    return language


def create_session(db: Session, user: User, request: Request) -> tuple[str, AuthContext]:
    raw = new_session_token()
    row = UserSession(
        user_id=user.id,
        token_hash=hash_token(raw),
        expires_at=session_expiry(),
        ip=get_client_ip(request),
        user_agent=(request.headers.get("user-agent") or "")[:512],
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    context = AuthContext(
        user_id=user.id,
        username=user.username,
        role=user.role,
        language=user.language,
        theme=user.theme,
        session_id=row.id,
        session_token=raw,
        csrf_token=csrf_token_for(raw),
    )
    return raw, context


def revoke_session(db: Session, session_id: int) -> None:
    row = db.get(UserSession, session_id)
    if row is not None and row.revoked_at is None:
        row.revoked_at = utcnow()
        db.commit()


def revoke_user_sessions(db: Session, user_id: int, *, except_session_id: int | None = None) -> None:
    query = select(UserSession).where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
    if except_session_id is not None:
        query = query.where(UserSession.id != except_session_id)
    now = utcnow()
    for session in db.scalars(query):
        session.revoked_at = now
    db.commit()


def list_user_sessions(db: Session, user_id: int) -> list[UserSession]:
    now = utcnow()
    return list(
        db.scalars(
            select(UserSession)
            .where(
                UserSession.user_id == user_id,
                UserSession.revoked_at.is_(None),
                UserSession.expires_at > now,
            )
            .order_by(UserSession.last_seen_at.desc(), UserSession.id.desc())
        )
    )


def revoke_user_session(db: Session, user_id: int, session_id: int) -> UserSession:
    session = db.get(UserSession, session_id)
    if session is None or session.user_id != user_id or session.revoked_at is not None:
        raise AppError("auth.session_not_found")
    session.revoked_at = utcnow()
    db.commit()
    return session


def cleanup_sessions(db: Session) -> None:
    now = utcnow()
    db.execute(delete(UserSession).where(UserSession.expires_at < now))
    db.execute(
        delete(UserSession).where(
            UserSession.revoked_at.is_not(None),
            UserSession.revoked_at < now - timedelta(days=7),
        )
    )
    db.commit()


def login(db: Session, request: Request, username: str, password: str) -> tuple[User, AuthContext, str]:
    username_key = normalize_username(username)[:64]
    ip = get_client_ip(request)
    check_login_allowed(db, username_key=username_key, ip=ip)
    user = db.scalar(select(User).where(User.username_key == username_key))
    if user is None:
        dummy_verify(password)
        record_attempt(db, username_key=username_key, ip=ip, succeeded=False)
        db.commit()
        add_audit(
            db,
            actor=None,
            actor_username=username_key,
            actor_role="anonymous",
            action_code="auth.login_failed",
            action_params={"reason": "invalid_credentials"},
            request=request,
        )
        db.commit()
        raise AppError("auth.invalid_credentials")
    if not verify_password(password, user.password_hash) or not user.is_active:
        if not user.is_active:
            verify_password(password, user.password_hash)
        record_attempt(db, username_key=username_key, ip=ip, succeeded=False)
        add_audit(
            db,
            actor=None,
            actor_username=user.username,
            actor_role=user.role,
            action_code="auth.login_failed",
            action_params={"reason": "disabled" if not user.is_active else "invalid_credentials"},
            request=request,
        )
        db.commit()
        raise AppError("auth.invalid_credentials")

    clear_failures(db, username_key=username_key, ip=ip)
    record_attempt(db, username_key=username_key, ip=ip, succeeded=True)
    user.last_login_at = utcnow()
    db.commit()
    if mfa_is_enabled(user):
        challenge = create_challenge(db, user)
        add_audit(
            db,
            actor=None,
            actor_username=user.username,
            actor_role=user.role,
            action_code="auth.mfa_challenge_issued",
            target_type="user",
            target_id=user.id,
            request=request,
        )
        db.commit()
        raise challenge
    raw, context = create_session(db, user, request)
    add_audit(db, actor=context, action_code="auth.login_succeeded", request=request)
    db.commit()
    return user, context, raw


def setup_admin(
    db: Session,
    request: Request,
    *,
    username: str,
    password: str,
    language: str,
    theme: str = "system",
) -> tuple[User, AuthContext, str]:
    with _SETUP_LOCK:
        if db.scalar(select(func.count(User.id))) > 0:
            raise AppError("setup.completed")
        username = validate_username(username)
        policy = validate_new_password(db, password, username)
        language = validate_language(language)
        user = User(
            username=username,
            username_key=normalize_username(username),
            password_hash=hash_password(password),
            role="admin",
            language=language,
            theme=theme,
            is_active=True,
        )
        db.add(user)
        state = ensure_system_state(db)
        state.setup_completed_at = utcnow()
        db.commit()
        db.refresh(user)
        record_password(db, user, user.password_hash, keep=policy.history_count)
        db.commit()
        raw, context = create_session(db, user, request)
        add_audit(db, actor=context, action_code="setup.completed", request=request)
        db.commit()
        return user, context, raw


def bootstrap_admin(db: Session) -> None:
    if db.scalar(select(func.count(User.id))) > 0:
        return
    username = settings.bootstrap_admin_username.strip()
    password = settings.bootstrap_admin_password
    if not username or not password:
        if username or password:
            logger.warning("Ignoring incomplete BOOTSTRAP_ADMIN_* configuration; the setup wizard remains enabled")
        return
    try:
        username = validate_username(username)
        policy = validate_new_password(db, password, username)
        language = settings.bootstrap_admin_language
        if language not in settings.available_languages:
            language = settings.resolved_default_language
    except AppError as exc:
        raise RuntimeError(f"Invalid bootstrap administrator configuration: {exc.code}") from exc
    user = User(
        username=username,
        username_key=normalize_username(username),
        password_hash=hash_password(password),
        role="admin",
        language=language,
        theme="system",
        is_active=True,
    )
    db.add(user)
    state = ensure_system_state(db)
    state.setup_completed_at = utcnow()
    db.commit()
    db.refresh(user)
    record_password(db, user, user.password_hash, keep=policy.history_count)
    db.commit()
    add_audit(
        db,
        actor=None,
        actor_username="system",
        actor_role="system",
        action_code="setup.bootstrap_admin",
        action_params={"username": username},
    )
    db.commit()


def change_password(
    db: Session,
    context: AuthContext,
    request: Request,
    *,
    current_password: str,
    new_password: str,
) -> tuple[str, AuthContext]:
    user = db.get(User, context.user_id)
    if user is None or not verify_password(current_password, user.password_hash):
        raise AppError("auth.invalid_current_password")
    policy = validate_new_password(db, new_password, user.username)
    if verify_password(new_password, user.password_hash):
        raise AppError("auth.weak_password", params={"reason": "same_as_current"})
    assert_not_reused(db, user, new_password, policy)
    user.password_hash = hash_password(new_password)
    user.password_changed_at = utcnow()
    record_password(db, user, user.password_hash, keep=policy.history_count)
    revoke_user_sessions(db, user.id, except_session_id=None)
    db.commit()
    raw, new_context = create_session(db, user, request)
    add_audit(db, actor=new_context, action_code="auth.password_changed", request=request)
    db.commit()
    return raw, new_context


def update_profile(
    db: Session,
    context: AuthContext,
    *,
    changes: dict[str, Any],
) -> User:
    user = db.get(User, context.user_id)
    if user is None:
        raise AppError("auth.unauthenticated")
    if "language" in changes and changes["language"] is not None:
        user.language = validate_language(changes["language"])
    if "theme" in changes and changes["theme"] is not None:
        if changes["theme"] not in {"light", "dark", "system"}:
            raise AppError("validation.invalid_choice", params={"field": "theme"})
        user.theme = changes["theme"]
    if "full_name" in changes:
        user.full_name = changes["full_name"]
    if "email" in changes:
        user.email = changes["email"]
    db.commit()
    db.refresh(user)
    return user
