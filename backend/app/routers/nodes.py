from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, File, Form, Query, Request, Response, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..audit import add_audit
from ..auth_deps import get_auth_context, require_operator
from ..backup_service import create_backup_node_job
from ..db import get_db
from ..diffing import diff_texts
from ..errors import AppError
from ..hostkey_service import trust_host_key
from ..jobs import serialize_job
from ..models import BackupRun, Node
from ..node_service import (
    bulk_action,
    create_node,
    delete_node,
    export_csv,
    get_node,
    import_csv,
    list_nodes,
    node_status,
    serialize_node,
    update_node,
)
from ..node_test_service import test_connection
from ..schemas import NodeBulkRequest, NodeCreate, NodeUpdate
from ..security import AuthContext
from ..version_service import current_config

router = APIRouter(prefix="/nodes", tags=["nodes"])


@router.get("")
def nodes_list(
    search: str | None = Query(default=None, max_length=253),
    group: str | None = Query(default=None, max_length=128),
    model: str | None = Query(default=None, max_length=128),
    status: Literal["ok", "failed", "pending", "never"] | None = Query(default=None, alias="status"),
    sort: str = Query(default="name"),
    order: Literal["asc", "desc"] = "asc",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
    context: AuthContext = Depends(get_auth_context),
):
    return list_nodes(
        db,
        role=context.role,
        search=search,
        group_name=group,
        model=model,
        status_filter=status,
        sort=sort,
        order=order,
        page=page,
        page_size=page_size,
    )


@router.get("/export.csv")
def export_nodes(
    db: Session = Depends(get_db),
    _context: AuthContext = Depends(require_operator),
):
    content = export_csv(db)
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="oxidized-nodes.csv"'},
    )


@router.post("", status_code=201)
def create_node_route(
    payload: NodeCreate,
    request: Request,
    db: Session = Depends(get_db),
    context: AuthContext = Depends(require_operator),
):
    previous_count = db.scalar(select(func.count(Node.id))) or 0
    result = create_node(
        db,
        payload=payload,
        actor=context,
        request=request,
        previous_count=previous_count,
    )
    return result


@router.post("/bulk")
def bulk_nodes(
    payload: NodeBulkRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    context: AuthContext = Depends(require_operator),
):
    if len(payload.ids) > 1000:
        raise AppError("node.bulk_too_large")
    result = bulk_action(
        db,
        action=payload.action,
        ids=payload.ids,
        group_name=payload.group_name,
        actor=context,
        request=request,
        model=payload.model,
        input=payload.input,
        port=payload.port,
        vars=payload.vars,
    )
    if "job_id" in result:
        response.status_code = 202
    return result


@router.post("/import")
def import_nodes(
    request: Request,
    file: UploadFile = File(...),
    mode: str = Form(default="skip_existing"),
    dry_run: bool = Form(default=False),
    db: Session = Depends(get_db),
    context: AuthContext = Depends(require_operator),
):
    if mode not in {"skip_existing", "update_existing"}:
        raise AppError("validation.invalid_choice", params={"field": "mode"})
    content = file.file.read(5_000_001)
    return import_csv(
        db,
        content=content,
        mode=mode,
        dry_run=dry_run,
        actor=context,
        request=request,
    )




@router.get("/compare")
def compare_nodes(
    left_id: int = Query(ge=1),
    right_id: int = Query(ge=1),
    db: Session = Depends(get_db),
    _context: AuthContext = Depends(get_auth_context),
):
    if left_id == right_id:
        raise AppError("validation.invalid_format", params={"field": "node_id"})
    left = get_node(db, left_id)
    right = get_node(db, right_id)
    left_config = current_config(db, left)
    right_config = current_config(db, right)
    return {
        "left": {"id": left.id, "name": left.name},
        "right": {"id": right.id, "name": right.name},
        "diff": diff_texts(left_config, right_config, from_name=left.name, to_name=right.name),
    }


@router.get("/{node_id}")
def node_detail(
    node_id: int,
    db: Session = Depends(get_db),
    context: AuthContext = Depends(get_auth_context),
):
    node = get_node(db, node_id)
    return serialize_node(db, node, role=context.role)


@router.patch("/{node_id}")
def node_update(
    node_id: int,
    payload: NodeUpdate,
    request: Request,
    db: Session = Depends(get_db),
    context: AuthContext = Depends(require_operator),
):
    return update_node(db, node_id=node_id, payload=payload, actor=context, request=request)


@router.delete("/{node_id}")
def node_delete(
    node_id: int,
    request: Request,
    db: Session = Depends(get_db),
    context: AuthContext = Depends(require_operator),
):
    return delete_node(db, node_id=node_id, actor=context, request=request)


@router.post("/{node_id}/backup", status_code=202)
def node_backup(
    node_id: int,
    request: Request,
    db: Session = Depends(get_db),
    context: AuthContext = Depends(require_operator),
):
    node = get_node(db, node_id)
    job = create_backup_node_job(db, node=node, actor=context, request=request)
    return serialize_job(db, job)


@router.post("/{node_id}/test-connection")
def node_test_connection(
    node_id: int,
    request: Request,
    db: Session = Depends(get_db),
    context: AuthContext = Depends(require_operator),
):
    node = get_node(db, node_id)
    result = test_connection(db, node)
    add_audit(
        db,
        actor=context,
        action_code="node.connection_tested",
        action_params={
            "name": node.name,
            "tcp": result["tcp"],
            "ssh": result["ssh"],
            "authenticated": result["authenticated"],
            "message": result["message"],
        },
        target_type="node",
        target_id=node.id,
        request=request,
    )
    db.commit()
    return result


@router.post("/{node_id}/trust-host-key")
def node_trust_host_key(
    node_id: int,
    request: Request,
    db: Session = Depends(get_db),
    context: AuthContext = Depends(require_operator),
):
    node = get_node(db, node_id)
    return trust_host_key(db, node, actor=context, request=request)



@router.get("/{node_id}/history")
def node_history(
    node_id: int,
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    _context: AuthContext = Depends(get_auth_context),
):
    node = get_node(db, node_id)
    rows = db.scalars(
        select(BackupRun).where(BackupRun.node_id == node.id).order_by(BackupRun.started_at.desc()).limit(limit)
    ).all()
    total = len(rows)
    success = sum(1 for row in rows if row.status == "success")
    return {
        "node_id": node.id,
        "total": total,
        "success_rate": (success / total) if total else None,
        "items": [
            {
                "id": row.id,
                "status": row.status,
                "trigger": row.trigger,
                "started_at": row.started_at.isoformat() if row.started_at else None,
                "finished_at": row.finished_at.isoformat() if row.finished_at else None,
                "duration_seconds": row.duration_seconds,
            }
            for row in rows
        ],
    }
@router.get("/{node_id}/status")
def node_status_route(
    node_id: int,
    refresh: bool = Query(default=False),
    db: Session = Depends(get_db),
    context: AuthContext = Depends(get_auth_context),
):
    node = get_node(db, node_id)
    result = node_status(db, node, refresh=refresh)
    if context.role == "viewer":
        result["last_error"] = None
    return result
