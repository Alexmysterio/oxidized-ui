from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.orm import Session

from .image_service import read_image, write_atomic
from .models import SystemSettings
from .settings import settings
from .timeutil import utcnow


def branding_dir() -> Path:
    return settings.data_dir / "branding"


def logo_path(row: SystemSettings) -> Path | None:
    if not row.logo_filename:
        return None
    path = branding_dir() / row.logo_filename
    return path if path.is_file() else None


def save_logo(db: Session, row: SystemSettings, upload: UploadFile) -> SystemSettings:
    data, extension = read_image(upload)
    filename = f"logo-{uuid.uuid4().hex}{extension}"
    write_atomic(branding_dir() / filename, data)
    previous = row.logo_filename
    row.logo_filename = filename
    row.updated_at = utcnow()
    db.commit()
    db.refresh(row)
    if previous:
        try:
            (branding_dir() / previous).unlink(missing_ok=True)
        except OSError:
            pass
    return row


def delete_logo(db: Session, row: SystemSettings) -> SystemSettings:
    previous = row.logo_filename
    row.logo_filename = None
    row.updated_at = utcnow()
    db.commit()
    db.refresh(row)
    if previous:
        try:
            (branding_dir() / previous).unlink(missing_ok=True)
        except OSError:
            pass
    return row
