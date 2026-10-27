from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ..auth_deps import get_auth_context, require_operator
from ..db import get_db
from ..reconciliation_service import compare, import_nodes
from ..schemas import ReconciliationImport
from ..security import AuthContext

router = APIRouter(prefix="/reconciliation", tags=["reconciliation"])


@router.get("")
def reconciliation(
    db: Session = Depends(get_db),
    context: AuthContext = Depends(get_auth_context),
):
    return compare(db, allowed_groups=context.scope_groups)


@router.post("/import", status_code=202)
def reconciliation_import(
    payload: ReconciliationImport,
    request: Request,
    db: Session = Depends(get_db),
    context: AuthContext = Depends(require_operator),
):
    names = [str(name) for name in payload.names]
    return import_nodes(db, names=names, actor=context, request=request)
