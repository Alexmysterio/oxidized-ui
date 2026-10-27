from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from ..audit import add_audit
from ..auth_deps import get_auth_context, require_operator
from ..db import get_db
from ..maintenance_service import create_window, delete_window, list_windows
from ..schemas import MaintenanceWindowCreate
from ..scope_service import ensure_scope_covers_windows
from ..security import AuthContext
from ..timeutil import to_iso

router = APIRouter(prefix="/maintenance", tags=["maintenance"])


@router.get("")
def maintenance_windows(
    include_finished: bool = Query(default=False),
    db: Session = Depends(get_db),
    context: AuthContext = Depends(get_auth_context),
):
    items = list_windows(db, include_finished=include_finished)
    if context.scope_groups is not None:
        scope = set(context.scope_groups)
        items = [
            item
            for item in items
            if item["scope_type"] == "group" and item["group_name"] in scope
            or item["scope_type"] == "node" and item["group_name"] in scope
        ]
    return {"items": items}


@router.post("", status_code=201)
def create_maintenance_window(
    payload: MaintenanceWindowCreate,
    request: Request,
    db: Session = Depends(get_db),
    context: AuthContext = Depends(require_operator),
):
    row = create_window(
        db,
        scope_type=payload.scope_type,
        node_id=payload.node_id,
        group_name=payload.group_name,
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
        reason=payload.reason,
        actor=context,
    )
    add_audit(
        db,
        actor=context,
        action_code="maintenance.created",
        action_params={
            "scope_type": row.scope_type,
            "group_name": row.group_name,
            "node_id": row.node_id,
            "ends_at": to_iso(row.ends_at),
        },
        target_type="maintenance",
        target_id=row.id,
        request=request,
    )
    db.commit()
    return {"id": row.id}


@router.delete("/{window_id}", status_code=204)
def delete_maintenance_window(
    window_id: int,
    request: Request,
    db: Session = Depends(get_db),
    context: AuthContext = Depends(require_operator),
):
    from ..models import MaintenanceWindow

    row = db.get(MaintenanceWindow, window_id)
    if row is not None:
        ensure_scope_covers_windows(db, context, row)
    delete_window(db, window_id)
    add_audit(
        db,
        actor=context,
        action_code="maintenance.deleted",
        action_params={"window_id": window_id},
        target_type="maintenance",
        target_id=window_id,
        request=request,
    )
    db.commit()
    return Response(status_code=204)
