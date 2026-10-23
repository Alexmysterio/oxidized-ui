from __future__ import annotations

import secrets
from datetime import timedelta
from typing import Any

import pyotp
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .crypto import decrypt_optional, encrypt_optional
from .errors import AppError
from .models import MfaChallenge, MfaRecoveryCode, User
from .security import hash_password, hash_token, new_session_token, verify_password
from .timeutil import to_iso, utcnow

MFA_ISSUER = "Oxidized UI"
CHALLENGE_MINUTES = 5
MAX_ATTEMPTS = 5
RECOVERY_CODE_COUNT = 10


class MfaRequired(Exception):
    def __init__(self, token: str, expires_at: Any) -> None:
        self.token = token
        self.expires_at = expires_at
        super().__init__("mfa_required")


def is_enabled(user: User) -> bool:
    return bool(user.mfa_enabled_at and user.mfa_secret_ciphertext)


def _normalize_recovery(value: str) -> str:
    return value.strip().replace("-", "").replace(" ", "").upper()


def begin_setup(user: User) -> tuple[str, str]:
    if is_enabled(user):
        raise AppError("auth.mfa_already_enabled")
    secret = pyotp.random_base32()
    user.mfa_secret_ciphertext = encrypt_optional(secret)
    user.mfa_enabled_at = None
    uri = pyotp.TOTP(secret).provisioning_uri(name=user.username, issuer_name=MFA_ISSUER)
    return secret, uri


def verify_totp(user: User, code: str) -> bool:
    secret = decrypt_optional(user.mfa_secret_ciphertext)
    if not secret:
        return False
    normalized = code.strip().replace(" ", "")
    if not normalized.isdigit():
        return False
    return bool(pyotp.TOTP(secret).verify(normalized, valid_window=1))


def generate_recovery_codes(db: Session, user: User) -> list[str]:
    db.execute(delete(MfaRecoveryCode).where(MfaRecoveryCode.user_id == user.id))
    plaintext: list[str] = []
    for _ in range(RECOVERY_CODE_COUNT):
        raw = secrets.token_hex(4).upper()
        code = f"{raw[:4]}-{raw[4:]}"
        plaintext.append(code)
        db.add(MfaRecoveryCode(user_id=user.id, code_hash=hash_password(_normalize_recovery(code))))
    return plaintext


def verify_recovery_code(db: Session, user: User, code: str) -> bool:
    normalized = _normalize_recovery(code)
    if len(normalized) != 8:
        return False
    for row in db.scalars(
        select(MfaRecoveryCode).where(
            MfaRecoveryCode.user_id == user.id,
            MfaRecoveryCode.used_at.is_(None),
        )
    ):
        if verify_password(normalized, row.code_hash):
            row.used_at = utcnow()
            db.commit()
            return True
    return False


def remaining_recovery_codes(db: Session, user: User) -> int:
    return int(
        db.scalar(
            select(func.count(MfaRecoveryCode.id)).where(
                MfaRecoveryCode.user_id == user.id,
                MfaRecoveryCode.used_at.is_(None),
            )
        )
        or 0
    )


def create_challenge(db: Session, user: User) -> MfaRequired:
    raw = new_session_token()
    expires = utcnow() + timedelta(minutes=CHALLENGE_MINUTES)
    db.add(
        MfaChallenge(
            user_id=user.id,
            token_hash=hash_token(raw),
            expires_at=expires,
        )
    )
    db.commit()
    return MfaRequired(raw, expires)


def challenge_public(challenge: MfaRequired) -> dict[str, Any]:
    return {
        "mfa_required": True,
        "challenge_token": challenge.token,
        "expires_at": to_iso(challenge.expires_at),
    }


def verify_challenge(db: Session, token: str, code: str) -> User:
    row = db.scalar(select(MfaChallenge).where(MfaChallenge.token_hash == hash_token(token)))
    if row is None or row.consumed_at is not None:
        raise AppError("auth.mfa_challenge_invalid")
    if row.expires_at <= utcnow():
        raise AppError("auth.mfa_challenge_expired")
    if row.attempts >= MAX_ATTEMPTS:
        raise AppError("auth.mfa_too_many_attempts")
    user = db.get(User, row.user_id)
    if user is None or not user.is_active or not is_enabled(user):
        raise AppError("auth.mfa_challenge_invalid")
    if verify_totp(user, code) or verify_recovery_code(db, user, code):
        row.consumed_at = utcnow()
        db.commit()
        return user
    row.attempts += 1
    db.commit()
    raise AppError("auth.invalid_mfa_code")


def disable(db: Session, user: User) -> None:
    user.mfa_secret_ciphertext = None
    user.mfa_enabled_at = None
    db.execute(delete(MfaRecoveryCode).where(MfaRecoveryCode.user_id == user.id))
    db.commit()
