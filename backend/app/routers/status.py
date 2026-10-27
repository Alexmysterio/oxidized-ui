from __future__ import annotations

import hmac
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..audit import add_audit
from ..auth_deps import get_auth_context, require_admin, require_operator
from ..backup_schedule_service import count_nodes, create_schedule, delete_schedule
from ..backup_schedule_service import serialize as serialize_schedule
from ..backup_service import create_backup_all_job, run_backup_all_job
from ..db import get_db
from ..docker_api import client_for as docker_client_for
from ..errors import AppError
from ..jobs import Job, cancel_job, create_and_submit, serialize_job
from ..models import Job as JobModel
from ..oxidized import client_for as oxidized_client_for
from ..schemas import BackupAllRequest, BackupScheduleCreate
from ..security import AuthContext
from ..settings import settings
from ..status_service import build_status

router = APIRouter(tags=["status"])


def _restart_runner(db: Session, job: Job) -> dict:
    docker_client_for(db).restart()
    job.progress_done = 1
    job.progress_total = 1
    db.commit()
    return {"restarted": True}


@router.get("/status")
def get_status(
    db: Session = Depends(get_db),
    _context: AuthContext = Depends(get_auth_context),
):
    return build_status(db)


@router.post("/backups/all", status_code=202)
def backup_all(
    request: Request,
    payload: BackupAllRequest | None = None,
    db: Session = Depends(get_db),
    context: AuthContext = Depends(require_operator),
):
    job = create_backup_all_job(
        db,
        actor=context,
        node_ids=payload.ids if payload is not None else None,
        request=request,
    )
    return serialize_job(db, job)


@router.post("/oxidized/reload")
def reload_oxidized(
    request: Request,
    db: Session = Depends(get_db),
    context: AuthContext = Depends(require_operator),
):
    try:
        oxidized_client_for(db).reload()
    except AppError:
        raise
    add_audit(
        db,
        actor=context,
        action_code="oxidized.reload_requested",
        target_type="oxidized",
        target_id="reload",
        request=request,
    )
    db.commit()
    return {"reloaded": True}


@router.post("/oxidized/restart", status_code=202)
def restart_oxidized(
    request: Request,
    db: Session = Depends(get_db),
    context: AuthContext = Depends(require_admin),
):
    job = create_and_submit(
        db,
        kind="oxidized_restart",
        actor_id=context.user_id,
        payload={"reason": "manual"},
        progress_total=1,
        runner=_restart_runner,
    )
    add_audit(
        db,
        actor=context,
        action_code="oxidized.restart_requested",
        action_params={"job_id": job.id},
        target_type="oxidized",
        target_id="restart",
        request=request,
    )
    db.commit()
    return serialize_job(db, job)




@router.post("/hooks/backup", status_code=202)
def inbound_backup_webhook(
    request: Request,
    db: Session = Depends(get_db),
):
    token = request.headers.get("x-webhook-token", "")
    expected = settings.inbound_webhook_token
    if not expected:
        raise AppError("app.not_found", params={"resource": "webhook"})
    if not token or not hmac.compare_digest(token, expected):
        raise AppError("auth.forbidden")
    active = db.scalar(select(Job).where(Job.kind == "backup_all", Job.status.in_(("queued", "running"))))
    if active is not None:
        raise AppError("job.already_running", params={"job_id": active.id})
    from ..models import Node

    nodes = list(db.scalars(select(Node)).all())
    if not nodes:
        raise AppError("node.not_found", params={"reason": "no_nodes"})
    job = create_and_submit(
        db,
        kind="backup_all",
        actor_id=None,
        payload={"node_ids": [node.id for node in nodes], "count": len(nodes), "source": "webhook"},
        progress_total=len(nodes),
        runner=run_backup_all_job,
    )
    return {"job_id": job.id, "requested": len(nodes)}


@router.get("/jobs")
def list_jobs(
    status: Literal["queued", "running", "succeeded", "failed", "cancelled"] | None = None,
    kind: Literal["backup_node", "backup_all", "oxidized_restart", "config_apply", "oxidized_reload"] | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
    _context: AuthContext = Depends(require_operator),
):
    filters = []
    if status:
        filters.append(JobModel.status == status)
    if kind:
        filters.append(JobModel.kind == kind)
    base = select(JobModel)
    count_query = select(func.count(JobModel.id))
    for condition in filters:
        base = base.where(condition)
        count_query = count_query.where(condition)
    total = db.scalar(count_query) or 0
    rows = db.scalars(base.order_by(JobModel.id.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return {
        "items": [serialize_job(db, row) for row in rows],
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": (total + page_size - 1) // page_size,
    }


@router.get("/jobs/{job_id}")
def get_job(
    job_id: int,
    db: Session = Depends(get_db),
    _context: AuthContext = Depends(require_operator),
):
    job = db.get(JobModel, job_id)
    if job is None:
        raise AppError("job.not_found", params={"job_id": job_id})
    return serialize_job(db, job)


@router.delete("/jobs/{job_id}", status_code=204)
def cancel_job_route(
    job_id: int,
    request: Request,
    db: Session = Depends(get_db),
    context: AuthContext = Depends(require_operator),
):
    job = cancel_job(db, job_id)
    add_audit(
        db,
        actor=context,
        action_code="job.cancelled",
        action_params={"job_id": job.id, "kind": job.kind},
        target_type="job",
        target_id=job.id,
        request=request,
    )
    db.commit()
    return Response(status_code=204)


@router.get("/backups/schedules")
def list_backup_schedules(db: Session = Depends(get_db), _context: AuthContext = Depends(require_operator)):
    from sqlalchemy import select

    from ..config_service import applied_config
    from ..models import BackupSchedule, Node
    rows = db.scalars(select(BackupSchedule).order_by(BackupSchedule.id)).all()
    counts: dict[str | None, int] = {
        group_name: int(count)
        for group_name, count in db.execute(
            select(Node.group_name, func.count(Node.id)).group_by(Node.group_name)
        ).all()
    }
    total_nodes = sum(counts.values())
    config = applied_config(db)
    configured_groups = config.get("groups") or {}
    group_names = sorted(
        {name for name in configured_groups if isinstance(name, str)} | {name for name in counts if name is not None}
    )
    items = []
    for row in rows:
        data = serialize_schedule(row)
        data["node_count"] = counts.get(row.group_name, 0) if row.group_name else total_nodes
        items.append(data)
    interval = config.get("interval")
    return {
        "items": items,
        "groups": [{"name": name, "node_count": counts.get(name, 0)} for name in group_names],
        "ungrouped_count": counts.get(None, 0),
        "total_nodes": total_nodes,
        "oxidized_interval_seconds": int(interval) if isinstance(interval, (int, float)) else None,
    }


@router.post("/backups/schedules", status_code=201)
def create_backup_schedule(
    payload: BackupScheduleCreate,
    db: Session = Depends(get_db),
    context: AuthContext = Depends(require_operator),
):
    row = create_schedule(
        db,
        group_name=payload.group_name,
        interval_minutes=payload.interval_minutes,
        actor_id=context.user_id,
    )
    created = serialize_schedule(row)
    created["node_count"] = count_nodes(db, row.group_name)
    return created


@router.delete("/backups/schedules/{schedule_id}", status_code=204)
def delete_backup_schedule(
    schedule_id: int,
    db: Session = Depends(get_db),
    _context: AuthContext = Depends(require_operator),
):
    delete_schedule(db, schedule_id)
    return Response(status_code=204)
