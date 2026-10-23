from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from ..config_service import health_config_writable
from ..db import get_db
from ..models import User
from ..oidc_service import enabled as oidc_enabled
from ..settings import settings
from ..system_service import get_settings_row

router = APIRouter(tags=["meta"])


@router.get("/meta")
def meta(db: Session = Depends(get_db)) -> dict:
    setup_required = (db.scalar(select(func.count(User.id))) or 0) == 0
    return {
        "setup_required": setup_required,
        "oidc_enabled": oidc_enabled(),
        "available_languages": settings.available_languages,
        "default_language": settings.resolved_default_language,
        "app_version": settings.app_version,
        "timezone": get_settings_row(db).timezone,
    }


@router.get("/health")
def health(db: Session = Depends(get_db)) -> JSONResponse:
    database_ok = True
    try:
        db.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001 - health endpoint must answer
        database_ok = False
    config_writable = health_config_writable()
    setup_required = True
    if database_ok:
        try:
            setup_required = (db.scalar(select(func.count(User.id))) or 0) == 0
        except Exception:  # noqa: BLE001
            database_ok = False
    healthy = database_ok and config_writable
    payload = {
        "status": "ok" if healthy else "degraded",
        "database": "ok" if database_ok else "error",
        "config_writable": config_writable,
        "setup_required": setup_required,
    }
    return JSONResponse(status_code=200 if healthy else 503, content=payload)
