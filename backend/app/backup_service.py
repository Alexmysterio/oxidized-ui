from __future__ import annotations

import logging
from typing import Any

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .audit import add_audit
from .config_service import applied_config
from .errors import AppError
from .jobs import Job, create_and_submit, update_progress
from .models import Job as JobModel
from .models import Node
from .oxidized import client_for as oxidized_client_for
from .security import AuthContext

logger = logging.getLogger("oxidized_ui.backups")


def _next_adds_job(db: Session) -> bool:
    config = applied_config(db)
    return bool(config.get("next_adds_job", False))


def create_backup_node_job(
    db: Session,
    *,
    node: Node,
    actor: AuthContext,
    request: Request,
) -> JobModel:
    existing = db.scalar(
        select(JobModel).where(
            JobModel.kind == "backup_node",
            JobModel.node_id == node.id,
            JobModel.status.in_(("queued", "running")),
        )
    )
    if existing is not None:
        raise AppError("job.already_running", params={"job_id": existing.id})
    job = create_and_submit(
        db,
        kind="backup_node",
        actor_id=actor.user_id,
        payload={"node_id": node.id, "name": node.name},
        node_id=node.id,
        progress_total=1,
        runner=run_backup_node_job,
    )
    add_audit(
        db,
        actor=actor,
        action_code="node.backup_requested",
        action_params={"name": node.name, "scope": "node"},
        target_type="node",
        target_id=node.id,
        request=request,
    )
    db.commit()
    return job


def create_backup_all_job(
    db: Session,
    *,
    actor: AuthContext,
    node_ids: list[int] | None,
    request: Request,
) -> JobModel:
    nodes = list(db.scalars(select(Node).order_by(Node.name)).all())
    if node_ids is not None:
        selected = set(node_ids)
        nodes = [node for node in nodes if node.id in selected]
    if not nodes:
        raise AppError("node.not_found", params={"reason": "no_nodes"})
    existing = db.scalar(
        select(JobModel).where(
            JobModel.kind == "backup_all",
            JobModel.status.in_(("queued", "running")),
        )
    )
    if existing is not None:
        raise AppError("job.already_running", params={"job_id": existing.id})
    job = create_and_submit(
        db,
        kind="backup_all",
        actor_id=actor.user_id,
        payload={"node_ids": [node.id for node in nodes], "count": len(nodes)},
        progress_total=len(nodes),
        runner=run_backup_all_job,
    )
    add_audit(
        db,
        actor=actor,
        action_code="node.backup_requested",
        action_params={"scope": "all" if node_ids is None else "selection", "count": len(nodes)},
        target_type="node",
        request=request,
    )
    db.commit()
    return job


def run_backup_node_job(db: Session, job: Job) -> dict[str, Any]:
    node = db.get(Node, job.node_id) if job.node_id else None
    if node is None:
        raise AppError("node.not_found")
    client = oxidized_client_for(db)
    client.next_node(node.name)
    update_progress(db, job, done=1, total=1)
    result = {"name": node.name, "queued": 1, "ok": True}
    if not _next_adds_job(db):
        result["warnings"] = ["oxidized.next_adds_job_disabled"]
    return result


def run_backup_all_job(db: Session, job: Job) -> dict[str, Any]:
    node_ids = [int(node_id) for node_id in job.payload.get("node_ids", [])]
    nodes = list(db.scalars(select(Node).where(Node.id.in_(node_ids))).all())
    client = oxidized_client_for(db)
    queued = 0
    failures: list[dict[str, Any]] = []
    for index, node in enumerate(nodes, start=1):
        try:
            client.next_node(node.name)
            queued += 1
        except AppError as exc:
            failures.append({"id": node.id, "name": node.name, "code": exc.code})
        update_progress(db, job, done=index, total=len(nodes))
    result: dict[str, Any] = {
        "requested": len(nodes),
        "queued": queued,
        "failed": failures,
        "ok": not failures,
    }
    if failures:
        result["error_code"] = "node.backup_failed"
    if not _next_adds_job(db):
        result.setdefault("warnings", []).append("oxidized.next_adds_job_disabled")
    return result
