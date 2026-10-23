from __future__ import annotations

from datetime import timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .errors import AppError
from .models import LoginAttempt
from .system_service import ensure_system_settings
from .timeutil import utcnow


def _window_start(db: Session):
    row = ensure_system_settings(db)
    minutes = max(int(row.login_window_minutes or 15), int(row.login_lockout_minutes or 30))
    return utcnow() - timedelta(minutes=minutes)


def _limits(db: Session) -> tuple[int, int, int]:
    row = ensure_system_settings(db)
    return (
        max(1, int(row.login_max_failures_per_user or 5)),
        max(1, int(row.login_max_failures_per_ip or 20)),
        max(1, int(row.login_lockout_minutes or 30)),
    )


def check_login_allowed(db: Session, *, username_key: str, ip: str) -> None:
    since = _window_start(db)
    max_user, max_ip, lockout_minutes = _limits(db)
    user_failures = (
        db.scalar(
            select(func.count(LoginAttempt.id)).where(
                LoginAttempt.username_key == username_key,
                LoginAttempt.ip == ip,
                LoginAttempt.succeeded.is_(False),
                LoginAttempt.created_at >= since,
            )
        )
        or 0
    )
    ip_failures = (
        db.scalar(
            select(func.count(LoginAttempt.id)).where(
                LoginAttempt.ip == ip,
                LoginAttempt.succeeded.is_(False),
                LoginAttempt.created_at >= since,
            )
        )
        or 0
    )
    retry_after = lockout_minutes * 60
    if user_failures >= max_user:
        raise AppError(
            "auth.too_many_attempts",
            headers={"Retry-After": str(retry_after)},
            params={"retry_after_seconds": retry_after},
        )
    if ip_failures >= max_ip:
        raise AppError(
            "auth.too_many_attempts",
            headers={"Retry-After": str(retry_after)},
            params={"retry_after_seconds": retry_after},
        )


def record_attempt(db: Session, *, username_key: str, ip: str, succeeded: bool) -> None:
    db.add(LoginAttempt(username_key=username_key[:64], ip=ip[:64], succeeded=succeeded))
    # Keep the table bounded; nobody needs years of failed login rows.
    cutoff = utcnow() - timedelta(days=30)
    db.execute(delete(LoginAttempt).where(LoginAttempt.created_at < cutoff))


def clear_failures(db: Session, *, username_key: str, ip: str) -> None:
    db.execute(
        delete(LoginAttempt).where(
            LoginAttempt.username_key == username_key,
            LoginAttempt.ip == ip,
            LoginAttempt.succeeded.is_(False),
            LoginAttempt.created_at >= _window_start(db),
        )
    )
