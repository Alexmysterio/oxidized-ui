from __future__ import annotations

import base64
import hashlib
import secrets
import time
from typing import Any
from urllib.parse import urlencode

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth_service import create_session
from .errors import AppError
from .models import User
from .security import hash_password, normalize_username, validate_username
from .settings import settings

_STATES: dict[str, dict[str, Any]] = {}
_DISCOVERY: dict[str, Any] = {}


def enabled() -> bool:
    return bool(
        settings.oidc_enabled
        and settings.oidc_issuer
        and settings.oidc_client_id
        and settings.oidc_redirect_uri
    )


def _discovery() -> dict[str, Any]:
    now = time.time()
    if _DISCOVERY.get("expires", 0) > now:
        return _DISCOVERY["data"]
    issuer = settings.oidc_issuer.rstrip("/")
    response = httpx.get(f"{issuer}/.well-known/openid-configuration", timeout=10)
    response.raise_for_status()
    data = response.json()
    if data.get("issuer", "").rstrip("/") != issuer:
        raise AppError("auth.oidc_failed", params={"reason": "issuer_mismatch"})
    for key in ("authorization_endpoint", "token_endpoint", "userinfo_endpoint"):
        if not str(data.get(key, "")).startswith("https://"):
            raise AppError("auth.oidc_failed", params={"reason": "insecure_endpoint"})
    _DISCOVERY.update({"data": data, "expires": now + 3600})
    return data


def start_url() -> str:
    if not enabled():
        raise AppError("auth.oidc_disabled")
    data = _discovery()
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    _STATES[state] = {"verifier": verifier, "created": time.time()}
    params = {
        "response_type": "code",
        "client_id": settings.oidc_client_id,
        "redirect_uri": settings.oidc_redirect_uri,
        "scope": settings.oidc_scopes,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    return f"{data['authorization_endpoint']}?{urlencode(params)}"


def complete(db: Session, code: str, state: str, request) -> tuple[User, str, Any]:
    dance = _STATES.pop(state, None)
    if dance is None or time.time() - dance["created"] > 600:
        raise AppError("auth.oidc_failed", params={"reason": "state"})
    data = _discovery()
    token_response = httpx.post(
        data["token_endpoint"],
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": settings.oidc_redirect_uri,
            "client_id": settings.oidc_client_id,
            "code_verifier": dance["verifier"],
        },
        auth=(settings.oidc_client_id, settings.oidc_client_secret) if settings.oidc_client_secret else None,
        timeout=15,
    )
    token_response.raise_for_status()
    access_token = token_response.json().get("access_token")
    if not access_token:
        raise AppError("auth.oidc_failed", params={"reason": "token"})
    info_response = httpx.get(
        data["userinfo_endpoint"],
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=15,
    )
    info_response.raise_for_status()
    info = info_response.json()
    subject = str(info.get("sub") or "").strip()
    if not subject:
        raise AppError("auth.oidc_failed", params={"reason": "subject"})
    raw_name = f"oidc_{hashlib.sha256(subject.encode()).hexdigest()[:24]}"
    username = validate_username(raw_name)
    key = normalize_username(username)
    user = db.scalar(select(User).where(User.username_key == key))
    if user is None:
        if not settings.oidc_auto_create:
            raise AppError("auth.oidc_failed", params={"reason": "unknown_user"})
        if settings.oidc_default_role not in {"viewer", "operator", "admin"}:
            raise AppError("auth.oidc_failed", params={"reason": "role"})
        user = User(
            username=username,
            username_key=key,
            password_hash=hash_password(secrets.token_urlsafe(32)),
            role=settings.oidc_default_role,
            language=settings.default_language,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    if not user.is_active:
        raise AppError("auth.forbidden")
    raw, context = create_session(db, user, request)
    return user, raw, context
