from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.orm import Session

from .image_service import read_image, write_atomic
from .models import User
from .settings import settings
from .timeutil import utcnow


def avatars_dir() -> Path:
    return settings.data_dir / "avatars"


def avatar_path(user: User) -> Path | None:
    if not user.avatar_filename:
        return None
    path = avatars_dir() / user.avatar_filename
    return path if path.is_file() else None


def save_avatar(db: Session, user: User, upload: UploadFile) -> User:
    data, extension = read_image(upload)
    filename = f"user-{user.id}-{uuid.uuid4().hex}{extension}"
    write_atomic(avatars_dir() / filename, data, mode=0o644)
    previous = user.avatar_filename
    user.avatar_filename = filename
    user.updated_at = utcnow()
    db.commit()
    db.refresh(user)
    if previous:
        try:
            (avatars_dir() / previous).unlink(missing_ok=True)
        except OSError:
            pass
    return user


def delete_avatar(db: Session, user: User) -> User:
    previous = user.avatar_filename
    user.avatar_filename = None
    user.updated_at = utcnow()
    db.commit()
    db.refresh(user)
    if previous:
        try:
            (avatars_dir() / previous).unlink(missing_ok=True)
        except OSError:
            pass
    return user
