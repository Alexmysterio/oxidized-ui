from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from ..audit import add_audit
from ..auth_deps import require_admin
from ..db import get_db
from ..docker_api import client_for as docker_client_for
from ..encrypted_export import create_export
from ..errors import AppError
from ..notifications import notify_test
from ..oxidized import client_for as oxidized_client_for
from ..schemas import ConnectionTestRequest, ExportRequest, SystemSettingsUpdate
from ..security import AuthContext
from ..system_service import get_settings_row, settings_public, update_system_settings
from ..timeutil import utcnow

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/settings")
def read_settings(
    db: Session = Depends(get_db),
    _context: AuthContext = Depends(require_admin),
):
    return settings_public(get_settings_row(db))


@router.patch("/settings")
def patch_settings(
    payload: SystemSettingsUpdate,
    request: Request,
    db: Session = Depends(get_db),
    context: AuthContext = Depends(require_admin),
):
    patch = payload.model_dump(exclude_unset=True)
    row = update_system_settings(db, patch)
    add_audit(
        db,
        actor=context,
        action_code="system.settings_updated",
        action_params={"fields": sorted(patch)},
        target_type="system",
        target_id="settings",
        request=request,
    )
    db.commit()
    return settings_public(row)


@router.post("/test")
def test_connection(
    payload: ConnectionTestRequest,
    request: Request,
    db: Session = Depends(get_db),
    context: AuthContext = Depends(require_admin),
):
    if payload.target == "oxidized":
        try:
            nodes = oxidized_client_for(db).list_nodes()
        except AppError as exc:
            raise AppError("system.connection_failed", params={"target": "oxidized", "reason": exc.code}) from exc
        result = {"ok": True, "target": "oxidized", "nodes": len(nodes)}
    elif payload.target == "docker":
        try:
            state = docker_client_for(db).container_state()
        except AppError as exc:
            raise AppError("system.connection_failed", params={"target": "docker", "reason": exc.code}) from exc
        result = {"ok": True, "target": "docker", "state": state}
    else:
        raise AppError("validation.invalid_choice", params={"field": "target"})
    add_audit(
        db,
        actor=context,
        action_code="system.connection_test",
        action_params={"target": payload.target, "ok": True},
        target_type="system",
        request=request,
    )
    db.commit()
    return result




@router.post("/export")
def export_encrypted_backup(
    payload: ExportRequest,
    request: Request,
    db: Session = Depends(get_db),
    context: AuthContext = Depends(require_admin),
):
    content = create_export(payload.passphrase)
    add_audit(
        db,
        actor=context,
        action_code="system.export_created",
        action_params={"bytes": len(content)},
        target_type="system",
        target_id="export",
        request=request,
    )
    db.commit()
    filename = f"oxidized-ui-{utcnow().strftime('%Y%m%d-%H%M%S')}.oxui"
    return Response(
        content=content,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/notify-test")
def test_notification(
    db: Session = Depends(get_db),
    _context: AuthContext = Depends(require_admin),
):
    return {"ok": notify_test(db)}
