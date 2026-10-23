from __future__ import annotations

import hmac

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from ..db import get_db
from ..errors import AppError
from ..node_service import node_source_payload
from ..settings import settings

router = APIRouter(prefix="/internal", tags=["internal"], include_in_schema=False)


def _authorize(request: Request) -> None:
    supplied = request.headers.get("x-oxidized-source-token", "")
    if not supplied or not hmac.compare_digest(supplied, settings.oxidized_source_token):
        raise AppError("internal_source.unauthorized")


@router.get("/source/nodes")
@router.get("/source/nodes/{node_want:path}")
def source_nodes(
    request: Request,
    response: Response,
    node_want: str | None = None,
    db: Session = Depends(get_db),
):
    _authorize(request)
    rows = node_source_payload(db)
    if node_want:
        wanted = node_want.rstrip("/")
        rows = [row for row in rows if row["name"] == wanted or row.get("group", "") + "/" + row["name"] == wanted]
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return rows
