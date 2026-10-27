from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..auth_deps import get_auth_context
from ..db import get_db
from ..schemas import SearchRequest
from ..search_service import config_search, global_search
from ..security import AuthContext

router = APIRouter(tags=["search"])


@router.get("/search")
def search_route(
    q: str = Query(min_length=1, max_length=100),
    db: Session = Depends(get_db),
    context: AuthContext = Depends(get_auth_context),
):
    return global_search(db, q, context.role, allowed_groups=context.scope_groups)


@router.post("/search/configs")
def config_search_route(
    payload: SearchRequest,
    db: Session = Depends(get_db),
    context: AuthContext = Depends(get_auth_context),
):
    return {"matches": config_search(db, payload.query, allowed_groups=context.scope_groups)}
