from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import Request

from .errors import AppError
from .settings import settings

USERNAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,63}$")

_hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4, hash_len=32, salt_len=16)
_dummy_hash: str | None = None

CAPABILITIES: dict[str, tuple[str, ...]] = {
    "admin": (
        "nodes.read",
        "nodes.write",
        "backups.trigger",
        "versions.read",
        "config.read",
        "config.write",
        "config.apply",
        "groups.write",
        "logs.read",
        "jobs.read",
        "users.manage",
        "audit.read",
        "system.manage",
        "compliance.read",
        "compliance.write",
        "me.write",
    ),
    "operator": (
        "nodes.read",
        "nodes.write",
        "backups.trigger",
        "versions.read",
        "groups.write",
        "logs.read",
        "jobs.read",
        "compliance.read",
        "compliance.write",
        "me.write",
    ),
    "viewer": ("nodes.read", "versions.read", "compliance.read", "me.write"),
}


def normalize_username(username: str) -> str:
    return username.strip().casefold()


def validate_username(username: str) -> str:
    username = username.strip()
    if not USERNAME_RE.fullmatch(username):
        raise AppError("validation.invalid_format", params={"field": "username"})
    return username


def validate_password(
    password: str,
    username: str | None = None,
    *,
    min_length: int = 12,
    require_complexity: bool = True,
) -> None:
    if password is None:
        raise AppError("validation.required", params={"field": "password"})
    if len(password) < min_length:
        raise AppError("auth.weak_password", params={"reason": "too_short", "min_length": min_length})
    if len(password) > 512:
        raise AppError("auth.weak_password", params={"reason": "too_long"})
    if username and password.casefold() == username.casefold():
        raise AppError("auth.weak_password", params={"reason": "same_as_username"})
    classes = sum(
        bool(regex.search(password))
        for regex in (re.compile(r"[a-z]"), re.compile(r"[A-Z]"), re.compile(r"\d"), re.compile(r"[^A-Za-z0-9]"))
    )
    if require_complexity and classes < 3:
        raise AppError("auth.weak_password", params={"reason": "too_simple"})


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def dummy_verify(password: str) -> None:
    global _dummy_hash
    if _dummy_hash is None:
        _dummy_hash = _hasher.hash("dummy-password-not-used-anywhere")
    try:
        _hasher.verify(_dummy_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        pass


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def csrf_token_for(session_token: str) -> str:
    digest = hmac.new(
        settings.secret_key.encode("utf-8"),
        b"oxidized-ui-csrf:" + session_token.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def new_source_token() -> str:
    return secrets.token_urlsafe(32)


def capabilities_for(role: str) -> list[str]:
    return list(CAPABILITIES.get(role, ()))


def role_has(role: str, capability: str) -> bool:
    return capability in CAPABILITIES.get(role, ())


def get_client_ip(request: Request) -> str:
    if settings.trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",", 1)[0].strip()[:64]
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip.strip()[:64]
    if request.client:
        return request.client.host[:64]
    return "unknown"


def request_scheme(request: Request) -> str:
    if settings.trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-proto")
        if forwarded:
            return forwarded.split(",", 1)[0].strip().lower()
    return request.url.scheme


def expected_origin(request: Request) -> str:
    scheme = request_scheme(request)
    host = request.headers.get("host", "")
    if settings.trust_proxy_headers:
        forwarded_host = request.headers.get("x-forwarded-host")
        if forwarded_host:
            host = forwarded_host.split(",", 1)[0].strip()
    return f"{scheme}://{host}".rstrip("/")


def origin_is_allowed(request: Request) -> bool:
    origin = request.headers.get("origin")
    if origin:
        candidates = {origin.rstrip("/"), *settings.trusted_origin_list}
        return expected_origin(request) in candidates or origin.rstrip("/") in settings.trusted_origin_list
    referer = request.headers.get("referer")
    if not referer:
        return False
    try:
        from urllib.parse import urlsplit

        parts = urlsplit(referer)
        candidate = f"{parts.scheme}://{parts.netloc}".rstrip("/")
        return candidate == expected_origin(request) or candidate in settings.trusted_origin_list
    except ValueError:
        return False


@dataclass(slots=True)
class AuthContext:
    user_id: int
    username: str
    role: str
    language: str
    theme: str
    session_id: int
    session_token: str
    csrf_token: str
    scope_groups: list[str] | None = None

    @property
    def capabilities(self) -> list[str]:
        return capabilities_for(self.role)


def cookie_max_age() -> int:
    return int(timedelta(hours=settings.session_absolute_hours).total_seconds())


def session_expiry() -> Any:
    from .timeutil import utcnow

    return utcnow() + timedelta(hours=settings.session_absolute_hours)


def idle_expiry() -> Any:
    from .timeutil import utcnow

    return utcnow() - timedelta(minutes=settings.session_idle_minutes)
