from __future__ import annotations

from typing import Any

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .errors import AppError
from .models import NodeTemplate
from .node_service import create_node
from .schemas import NodeCreate, NodeTemplateApply, NodeTemplateCreate, NodeTemplateUpdate
from .scope_service import require_group
from .security import AuthContext
from .timeutil import utcnow


def serialize(row: NodeTemplate) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "model": row.model,
        "group_name": row.group_name,
        "input": row.input,
        "port": row.port,
        "username": row.username,
        "output": row.output,
        "prompt": row.prompt,
        "timeout_seconds": row.timeout_seconds,
        "vars": row.vars or {},
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def list_templates(db: Session) -> list[NodeTemplate]:
    return list(db.scalars(select(NodeTemplate).order_by(NodeTemplate.name)).all())


def _clean_name(name: str) -> str:
    value = (name or "").strip()
    if not value:
        raise AppError("validation.required", params={"field": "name"})
    return value[:100]


def create_template(db: Session, *, payload: NodeTemplateCreate, actor_id: int) -> NodeTemplate:
    name = _clean_name(payload.name)
    if db.scalar(select(NodeTemplate).where(NodeTemplate.name == name)) is not None:
        raise AppError("validation.duplicate", params={"field": "name"})
    row = NodeTemplate(
        name=name,
        model=payload.model,
        group_name=payload.group_name,
        input=payload.input,
        port=payload.port,
        username=payload.username,
        output=payload.output,
        prompt=payload.prompt,
        timeout_seconds=payload.timeout_seconds,
        vars=payload.vars or {},
        created_by_id=actor_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update_template(db: Session, template_id: int, payload: NodeTemplateUpdate) -> NodeTemplate:
    row = db.get(NodeTemplate, template_id)
    if row is None:
        raise AppError("app.not_found", params={"id": template_id})
    data = payload.model_dump(exclude_unset=True)
    if "name" in data and data["name"] is not None:
        name = _clean_name(data["name"])
        existing = db.scalar(select(NodeTemplate).where(NodeTemplate.name == name))
        if existing is not None and existing.id != template_id:
            raise AppError("validation.duplicate", params={"field": "name"})
        row.name = name
    for field in ("model", "group_name", "input", "port", "username", "output", "prompt", "timeout_seconds"):
        if field in data:
            setattr(row, field, data[field])
    if "vars" in data:
        row.vars = data["vars"] or {}
    row.updated_at = utcnow()
    db.commit()
    db.refresh(row)
    return row


def delete_template(db: Session, template_id: int) -> None:
    row = db.get(NodeTemplate, template_id)
    if row is None:
        raise AppError("app.not_found", params={"id": template_id})
    db.delete(row)
    db.commit()


def apply_template(
    db: Session,
    *,
    template_id: int,
    payload: NodeTemplateApply,
    actor: AuthContext,
    request: Request,
) -> dict[str, Any]:
    row = db.get(NodeTemplate, template_id)
    if row is None:
        raise AppError("app.not_found", params={"id": template_id})
    require_group(actor, row.group_name)
    node_payload = NodeCreate(
        name=payload.name,
        address=payload.address,
        model=row.model,
        group_name=row.group_name,
        input=row.input,
        port=row.port,
        username=row.username,
        output=row.output,
        prompt=row.prompt,
        timeout_seconds=row.timeout_seconds,
        vars=row.vars or {},
        tags=payload.tags,
    )
    from sqlalchemy import func

    from .models import Node

    previous_count = db.scalar(select(func.count(Node.id))) or 0
    return create_node(
        db,
        payload=node_payload,
        actor=actor,
        request=request,
        previous_count=previous_count,
    )
