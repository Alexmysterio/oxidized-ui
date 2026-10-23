from __future__ import annotations

import hmac

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from ..db import get_db
from ..errors import AppError
from ..metrics_service import render_metrics
from ..settings import settings

router = APIRouter(tags=["metrics"])


@router.get("/metrics")
def metrics(
    request: Request,
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
    x_metrics_token: str | None = Header(default=None),
):
    if settings.metrics_token:
        supplied = x_metrics_token or ""
        if authorization and authorization.lower().startswith("bearer "):
            supplied = authorization[7:].strip()
        if not supplied or not hmac.compare_digest(supplied, settings.metrics_token):
            raise AppError("auth.unauthenticated")
    return PlainTextResponse(render_metrics(db), media_type="text/plain; version=0.0.4")
