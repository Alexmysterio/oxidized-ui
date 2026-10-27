from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.orm import Session

from ..auth_deps import require_operator
from ..db import get_db
from ..log_service import download, snapshot, sse_events
from ..scope_service import require_unscoped
from ..security import AuthContext
from ..settings import settings
from ..system_service import ensure_system_settings

router = APIRouter(prefix="/logs", tags=["logs"])

LEVELS = ("trace", "debug", "info", "warn", "error", "fatal", "unknown")


@router.get("")
def logs_snapshot(
    tail: int | None = Query(default=None, ge=1, le=5000),
    since: str | None = Query(default=None, max_length=64),
    level: Literal["trace", "debug", "info", "warn", "error", "fatal", "unknown"] | None = None,
    q: str | None = Query(default=None, max_length=200),
    db: Session = Depends(get_db),
    context: AuthContext = Depends(require_operator),
):
    require_unscoped(context)
    if tail is None:
        tail = ensure_system_settings(db).log_tail_default or settings.max_log_lines
    return snapshot(db, tail=tail, level=level, query=q, since=since)


@router.get("/stream")
def logs_stream(
    request: Request,
    tail: int | None = Query(default=None, ge=1, le=5000),
    level: Literal["trace", "debug", "info", "warn", "error", "fatal", "unknown"] | None = None,
    q: str | None = Query(default=None, max_length=200),
    db: Session = Depends(get_db),
    context: AuthContext = Depends(require_operator),
):
    require_unscoped(context)
    if tail is None:
        tail = ensure_system_settings(db).log_tail_default or settings.max_log_lines
    from ..docker_api import client_for

    return StreamingResponse(
        sse_events(client_for(db), tail=tail, level=level, query=q, request=request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/download")
def logs_download(
    since: str | None = Query(default=None, max_length=64),
    until: str | None = Query(default=None, max_length=64),
    level: Literal["trace", "debug", "info", "warn", "error", "fatal", "unknown"] | None = None,
    q: str | None = Query(default=None, max_length=200),
    db: Session = Depends(get_db),
    context: AuthContext = Depends(require_operator),
):
    require_unscoped(context)
    filename, content = download(db, since=since, until=until, level=level, query=q)
    return Response(
        content=content,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
