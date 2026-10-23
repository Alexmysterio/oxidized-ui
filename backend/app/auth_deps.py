from __future__ import annotations

import hmac
from datetime import timedelta

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .api_token_service import authenticate_token, context_from_token
from .db import get_db
from .errors import AppError
from .models import User, UserSession
from .security import AuthContext, csrf_token_for, hash_token, role_has
from .settings import settings
from .timeutil import ensure_utc, utcnow


def _load_session(request: Request, db: Session) -> tuple[UserSession, User, str]:
    raw = request.cookies.get(settings.session_cookie_name)
    if not raw:
        raise AppError("auth.unauthenticated")
    session = db.scalar(select(UserSession).where(UserSession.token_hash == hash_token(raw)))
    if session is None:
        raise AppError("auth.unauthenticated")
    now = utcnow()
    last_seen = ensure_utc(session.last_seen_at)
    expires = ensure_utc(session.expires_at)
    if session.revoked_at is not None or expires is None or expires <= now:
        raise AppError("auth.session_expired")
    if last_seen and last_seen + timedelta(minutes=settings.session_idle_minutes) < now:
        session.revoked_at = now
        db.commit()
        raise AppError("auth.session_expired")

    user = db.get(User, session.user_id)
    if user is None or not user.is_active:
        raise AppError("auth.unauthenticated")
    if last_seen is None or now - last_seen > timedelta(seconds=60):
        session.last_seen_at = now
        db.commit()
    return session, user, raw


def get_auth_context(request: Request, db: Session = Depends(get_db)) -> AuthContext:
    authorization = request.headers.get("authorization", "")
    if authorization.lower().startswith("bearer "):
        raw = authorization[7:].strip()
        if raw:
            user, token = authenticate_token(db, raw)
            return context_from_token(user, token, raw)
    session, user, raw = _load_session(request, db)
    return AuthContext(
        user_id=user.id,
        username=user.username,
        role=user.role,
        language=user.language,
        theme=user.theme,
        session_id=session.id,
        session_token=raw,
        csrf_token=csrf_token_for(raw),
    )


def require_admin(ctx: AuthContext = Depends(get_auth_context)) -> AuthContext:
    if ctx.role != "admin":
        raise AppError("auth.forbidden")
    return ctx


def require_operator(ctx: AuthContext = Depends(get_auth_context)) -> AuthContext:
    if ctx.role not in {"admin", "operator"}:
        raise AppError("auth.forbidden")
    return ctx


def require_capability(capability: str):
    def dependency(ctx: AuthContext = Depends(get_auth_context)) -> AuthContext:
        if not role_has(ctx.role, capability):
            raise AppError("auth.forbidden")
        return ctx

    return dependency


def validate_csrf_header(request: Request) -> None:
    raw = request.cookies.get(settings.session_cookie_name)
    supplied = request.headers.get("x-csrf-token")
    if not raw or not supplied:
        raise AppError("auth.csrf_failed")
    expected = csrf_token_for(raw)
    if not hmac.compare_digest(expected, supplied):
        raise AppError("auth.csrf_failed")
