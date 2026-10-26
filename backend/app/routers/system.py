from __future__ import annotations

from fastapi import APIRouter, Depends, File, Request, Response, UploadFile
from sqlalchemy.orm import Session

from ..audit import add_audit
from ..auth_deps import require_admin
from ..branding_service import delete_logo, save_logo
from ..db import get_db
from ..docker_api import client_for as docker_client_for
from ..encrypted_export import create_export
from ..errors import AppError
from ..notifications import (
    channel_public,
    create_channel,
    delete_channel,
    list_channels,
    notify_test,
    update_channel,
)
from ..oxidized import client_for as oxidized_client_for
from ..schemas import (
    ConnectionTestRequest,
    ExportRequest,
    NotificationChannelCreate,
    NotificationChannelUpdate,
    SystemSettingsUpdate,
)
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


@router.get("/notifications")
def read_notifications(
    db: Session = Depends(get_db),
    _context: AuthContext = Depends(require_admin),
):
    return {"items": [channel_public(row) for row in list_channels(db)]}


@router.post("/notifications", status_code=201)
def create_notification(
    payload: NotificationChannelCreate,
    request: Request,
    db: Session = Depends(get_db),
    context: AuthContext = Depends(require_admin),
):
    row = create_channel(db, payload=payload)
    add_audit(
        db,
        actor=context,
        action_code="system.notification_created",
        action_params={"name": row.name, "kind": row.kind},
        target_type="system",
        target_id=row.id,
        request=request,
    )
    db.commit()
    return channel_public(row)


@router.patch("/notifications/{channel_id}")
def update_notification(
    channel_id: int,
    payload: NotificationChannelUpdate,
    request: Request,
    db: Session = Depends(get_db),
    context: AuthContext = Depends(require_admin),
):
    row = update_channel(db, channel_id, payload=payload)
    add_audit(
        db,
        actor=context,
        action_code="system.notification_updated",
        action_params={"name": row.name, "kind": row.kind},
        target_type="system",
        target_id=row.id,
        request=request,
    )
    db.commit()
    return channel_public(row)


@router.delete("/notifications/{channel_id}", status_code=204)
def delete_notification(
    channel_id: int,
    request: Request,
    db: Session = Depends(get_db),
    context: AuthContext = Depends(require_admin),
):
    delete_channel(db, channel_id)
    add_audit(
        db,
        actor=context,
        action_code="system.notification_deleted",
        action_params={"channel_id": channel_id},
        target_type="system",
        target_id=channel_id,
        request=request,
    )
    db.commit()
    return Response(status_code=204)


@router.post("/notifications/{channel_id}/test")
def test_notification_channel(
    channel_id: int,
    db: Session = Depends(get_db),
    _context: AuthContext = Depends(require_admin),
):
    return notify_test(db, channel_id)


@router.post("/branding/logo")
def upload_logo(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    context: AuthContext = Depends(require_admin),
):
    row = save_logo(db, get_settings_row(db), file)
    add_audit(
        db,
        actor=context,
        action_code="system.branding_updated",
        action_params={"logo": True},
        target_type="system",
        target_id="settings",
        request=request,
    )
    db.commit()
    return settings_public(row)


@router.delete("/branding/logo", status_code=204)
def remove_logo(
    request: Request,
    db: Session = Depends(get_db),
    context: AuthContext = Depends(require_admin),
):
    delete_logo(db, get_settings_row(db))
    add_audit(
        db,
        actor=context,
        action_code="system.branding_updated",
        action_params={"logo": False},
        target_type="system",
        target_id="settings",
        request=request,
    )
    db.commit()
    return Response(status_code=204)


@router.post("/notify-test")
def test_notification(
    db: Session = Depends(get_db),
    _context: AuthContext = Depends(require_admin),
):
    return notify_test(db)
