from __future__ import annotations

from fastapi import APIRouter, Depends, File, Request, Response, UploadFile
from sqlalchemy.orm import Session

from ..audit import add_audit
from ..auth_deps import require_admin, require_capability
from ..branding_service import delete_logo, save_logo
from ..db import get_db
from ..docker_api import client_for as docker_client_for
from ..encrypted_export import create_export
from ..errors import AppError
from ..export_service import configure as configure_export_target
from ..export_service import export_now, verify_bundle
from ..export_service import public_status as export_status
from ..health_service import snapshot as health_snapshot
from ..jobs import serialize_job
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
    ExportConfigPayload,
    ExportRequest,
    ExportVerifyRequest,
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


@router.get("/export")
def read_export_config(
    db: Session = Depends(get_db),
    _context: AuthContext = Depends(require_admin),
):
    return export_status(get_settings_row(db))


@router.put("/export")
def configure_export(
    payload: ExportConfigPayload,
    request: Request,
    db: Session = Depends(get_db),
    context: AuthContext = Depends(require_admin),
):
    row = configure_export_target(
        db,
        kind=payload.kind,
        config=payload.config,
        interval_hours=payload.interval_hours,
        enabled=payload.enabled,
    )
    add_audit(
        db,
        actor=context,
        action_code="system.export_configured",
        action_params={"kind": payload.kind, "enabled": payload.enabled},
        target_type="system",
        target_id="export",
        request=request,
    )
    db.commit()
    return export_status(row)


@router.post("/export/run", status_code=202)
def run_export(
    request: Request,
    db: Session = Depends(get_db),
    context: AuthContext = Depends(require_admin),
):
    job = export_now(db, actor_id=context.user_id)
    add_audit(
        db,
        actor=context,
        action_code="system.export_requested",
        action_params={"job_id": job.id},
        target_type="system",
        target_id="export",
        request=request,
    )
    db.commit()
    return serialize_job(db, job)


@router.get("/health")
def read_health(
    db: Session = Depends(get_db),
    _context: AuthContext = Depends(require_capability("logs.read")),
):
    return health_snapshot(db)


@router.get("/health/history")
def read_health_history(
    hours: int = 168,
    db: Session = Depends(get_db),
    _context: AuthContext = Depends(require_capability("logs.read")),
):
    from ..health_service import history

    return history(db, hours=hours)


@router.get("/email")
def read_email_config(
    db: Session = Depends(get_db),
    _context: AuthContext = Depends(require_admin),
):
    from ..email_service import status

    return status(db)


@router.post("/email/test")
def test_email(
    db: Session = Depends(get_db),
    _context: AuthContext = Depends(require_admin),
):
    from ..email_service import configured, send

    if not configured(db):
        return {"ok": False, "reason": "not_configured"}
    ok = send(db, subject="Oxidized UI test", body="SMTP delivery works.")
    return {"ok": ok}


@router.post("/export/verify")
def verify_export(
    payload: ExportVerifyRequest,
    request: Request,
    db: Session = Depends(get_db),
    context: AuthContext = Depends(require_admin),
):
    result = verify_bundle(db, payload.passphrase)
    add_audit(
        db,
        actor=context,
        action_code="system.export_verified",
        action_params={"ok": True, "entries": result.get("entries")},
        target_type="system",
        target_id="export",
        request=request,
    )
    db.commit()
    return result


@router.get("/reports")
def list_reports_route(
    db: Session = Depends(get_db),
    _context: AuthContext = Depends(require_admin),
):
    from ..report_service import list_reports
    from ..system_service import get_settings_row

    row = get_settings_row(db)
    return {
        "items": list_reports(),
        "last_run_at": row.report_last_run_at.isoformat() if row.report_last_run_at else None,
    }


@router.post("/reports/run", status_code=202)
def run_report_route(
    request: Request,
    db: Session = Depends(get_db),
    context: AuthContext = Depends(require_admin),
):
    from ..report_service import run_report_now

    job = run_report_now(db, actor=context)
    add_audit(
        db,
        actor=context,
        action_code="report.generated",
        action_params={"job_id": job.id},
        target_type="system",
        target_id="report",
        request=request,
    )
    db.commit()
    return serialize_job(db, job)


@router.get("/reports/{filename}")
def download_report(
    filename: str,
    db: Session = Depends(get_db),
    _context: AuthContext = Depends(require_admin),
):
    from ..report_service import report_path

    path = report_path(filename)
    return Response(
        content=path.read_bytes(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{path.name}"'},
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
