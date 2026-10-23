from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .errors import AppError
from .models import PasswordHistory, SystemSettings, User
from .security import validate_password, verify_password
from .system_service import ensure_system_settings
from .timeutil import utcnow


@dataclass(frozen=True, slots=True)
class PasswordPolicy:
    min_length: int
    require_complexity: bool
    history_count: int


def get_policy(db: Session) -> PasswordPolicy:
    row: SystemSettings = ensure_system_settings(db)
    return PasswordPolicy(
        min_length=int(row.password_min_length or 12),
        require_complexity=bool(row.password_require_complexity),
        history_count=max(0, int(row.password_history_count or 0)),
    )


def validate_new_password(db: Session, password: str, username: str | None = None) -> PasswordPolicy:
    policy = get_policy(db)
    validate_password(
        password,
        username,
        min_length=policy.min_length,
        require_complexity=policy.require_complexity,
    )
    return policy


def assert_not_reused(db: Session, user: User, password: str, policy: PasswordPolicy) -> None:
    if policy.history_count <= 0:
        return
    history = list(
        db.scalars(
            select(PasswordHistory)
            .where(PasswordHistory.user_id == user.id)
            .order_by(PasswordHistory.created_at.desc(), PasswordHistory.id.desc())
            .limit(policy.history_count)
        )
    )
    if verify_password(password, user.password_hash) or any(
        verify_password(password, item.password_hash) for item in history
    ):
        raise AppError("auth.password_reused", params={"count": policy.history_count})


def record_password(db: Session, user: User, password_hash: str, *, keep: int) -> None:
    db.add(PasswordHistory(user_id=user.id, password_hash=password_hash, created_at=utcnow()))
    db.flush()
    rows = list(
        db.scalars(
            select(PasswordHistory)
            .where(PasswordHistory.user_id == user.id)
            .order_by(PasswordHistory.created_at.desc(), PasswordHistory.id.desc())
        )
    )
    excess = rows[max(1, keep + 1) :]
    if excess:
        db.execute(delete(PasswordHistory).where(PasswordHistory.id.in_([row.id for row in excess])))
