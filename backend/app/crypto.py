from __future__ import annotations

import json
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from .errors import AppError
from .settings import settings

_cipher = Fernet(settings.fernet_key.encode("ascii"))


def encrypt_text(value: str) -> str:
    return _cipher.encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_text(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        return _cipher.decrypt(value.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError) as exc:
        raise AppError("app.internal_error") from exc


def encrypt_json(value: Any) -> str:
    return encrypt_text(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def decrypt_json(value: str | None, default: Any = None) -> Any:
    if value is None:
        return default
    try:
        return json.loads(decrypt_text(value) or "")
    except (json.JSONDecodeError, TypeError) as exc:
        raise AppError("app.internal_error") from exc


def encrypt_optional(value: str | None) -> str | None:
    return encrypt_text(value) if value else None


def decrypt_optional(value: str | None) -> str | None:
    return decrypt_text(value) if value else None
