from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from ..audit import add_audit
from ..auth_deps import get_auth_context, require_admin
from ..catalog import catalog
from ..config_service import (
    cancel_schedule,
    config_detail,
    create_draft,
    get_applied_revision,
    get_draft_revision,
    restore_revision,
    revision_detail,
    revision_diff,
    revisions_page,
    schedule_apply,
    scheduled_applies,
    serialize_schedule,
    start_apply,
    validate_payload,
)
from ..db import get_db
from ..errors import AppError
from ..jobs import serialize_job
from ..schemas import (
    ConfigApplyRequest,
    ConfigDraftRequest,
    ConfigRestoreRequest,
    ConfigScheduleRequest,
    ConfigValidateRequest,
)
from ..security import AuthContext

router = APIRouter(prefix="/config", tags=["config"])


@router.get("/catalog")
def get_catalog(
    _context: AuthContext = Depends(get_auth_context),
):
    return catalog()


@router.get("")
def get_config(
    db: Session = Depends(get_db),
    _context: AuthContext = Depends(require_admin),
):
    return config_detail(db)


@router.post("/validate")
def validate_config(
    payload: ConfigValidateRequest,
    db: Session = Depends(get_db),
    _context: AuthContext = Depends(require_admin),
):
    return validate_payload(db, config=payload.config, yaml_text=payload.yaml)


@router.post("/draft", status_code=201)
def save_draft(
    payload: ConfigDraftRequest,
    request: Request,
    db: Session = Depends(get_db),
    context: AuthContext = Depends(require_admin),
):
    revision = create_draft(
        db,
        config=payload.config,
        yaml_text=payload.yaml,
        expected_revision_id=payload.expected_revision_id,
        origin=payload.origin,
        actor_id=context.user_id,
        note=payload.note,
    )
    add_audit(
        db,
        actor=context,
        action_code="config.draft_saved",
        action_params={"revision_id": revision.id, "origin": payload.origin},
        target_type="config",
        target_id=revision.id,
        request=request,
    )
    db.commit()
    diff = revision_diff(db, revision, None)
    return {
        "revision": revision_detail(db, revision),
        "diff": diff,
        "requires_apply": True,
    }


@router.get("/revisions")
def list_revisions(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
    _context: AuthContext = Depends(require_admin),
):
    return revisions_page(db, page, page_size)


@router.get("/revisions/{revision_id}")
def get_revision(
    revision_id: int,
    db: Session = Depends(get_db),
    _context: AuthContext = Depends(require_admin),
):
    from ..models import ConfigRevision

    revision = db.get(ConfigRevision, revision_id)
    if revision is None:
        raise AppError("config.revision_not_found", params={"revision_id": revision_id})
    return revision_detail(db, revision)


@router.get("/revisions/{revision_id}/diff")
def revision_diff_route(
    revision_id: int,
    against: int | None = Query(default=None),
    db: Session = Depends(get_db),
    _context: AuthContext = Depends(require_admin),
):
    from ..models import ConfigRevision

    revision = db.get(ConfigRevision, revision_id)
    if revision is None:
        raise AppError("config.revision_not_found", params={"revision_id": revision_id})
    return revision_diff(db, revision, against)


@router.post("/revisions/{revision_id}/restore", status_code=201)
def restore_revision_route(
    revision_id: int,
    payload: ConfigRestoreRequest,
    request: Request,
    db: Session = Depends(get_db),
    context: AuthContext = Depends(require_admin),
):
    from ..models import ConfigRevision

    revision = db.get(ConfigRevision, revision_id)
    if revision is None:
        raise AppError("config.revision_not_found", params={"revision_id": revision_id})
    restored = restore_revision(
        db,
        revision,
        actor_id=context.user_id,
        note=payload.note,
    )
    add_audit(
        db,
        actor=context,
        action_code="config.draft_saved",
        action_params={"revision_id": restored.id, "origin": "rollback", "source_revision": revision_id},
        target_type="config",
        target_id=restored.id,
        request=request,
    )
    db.commit()
    return {
        "revision": revision_detail(db, restored),
        "diff": revision_diff(db, restored, None),
        "requires_apply": True,
    }


@router.post("/apply", status_code=202)
def apply_config(
    payload: ConfigApplyRequest,
    request: Request,
    db: Session = Depends(get_db),
    context: AuthContext = Depends(require_admin),
):
    job = start_apply(
        db,
        revision_id=payload.revision_id,
        restart=payload.restart,
        actor_id=context.user_id,
    )
    add_audit(
        db,
        actor=context,
        action_code="config.apply_requested",
        action_params={"revision_id": payload.revision_id, "job_id": job.id},
        target_type="config",
        target_id=payload.revision_id,
        request=request,
    )
    db.commit()
    return serialize_job(db, job)




@router.post("/schedule", status_code=201)
def schedule_config_apply(
    payload: ConfigScheduleRequest,
    request: Request,
    db: Session = Depends(get_db),
    context: AuthContext = Depends(require_admin),
):
    row = schedule_apply(db, revision_id=payload.revision_id, run_at=payload.run_at, actor_id=context.user_id)
    add_audit(
        db,
        actor=context,
        action_code="config.apply_scheduled",
        action_params={"revision_id": payload.revision_id, "schedule_id": row.id, "run_at": row.run_at.isoformat()},
        target_type="config",
        target_id=payload.revision_id,
        request=request,
    )
    db.commit()
    return serialize_schedule(row)


@router.get("/schedule")
def list_config_schedules(
    db: Session = Depends(get_db),
    _context: AuthContext = Depends(require_admin),
):
    return {"items": scheduled_applies(db)}


@router.delete("/schedule/{schedule_id}", status_code=204)
def cancel_config_schedule(
    schedule_id: int,
    request: Request,
    db: Session = Depends(get_db),
    context: AuthContext = Depends(require_admin),
):
    cancel_schedule(db, schedule_id)
    add_audit(
        db,
        actor=context,
        action_code="config.apply_schedule_cancelled",
        action_params={"schedule_id": schedule_id},
        target_type="config",
        target_id=schedule_id,
        request=request,
    )
    db.commit()
    return Response(status_code=204)

@router.get("/current-draft")
def current_draft(
    db: Session = Depends(get_db),
    _context: AuthContext = Depends(require_admin),
):
    draft = get_draft_revision(db)
    applied = get_applied_revision(db)
    return {
        "draft": revision_detail(db, draft) if draft else None,
        "applied": revision_detail(db, applied) if applied else None,
    }
