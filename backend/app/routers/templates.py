from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from ..audit import add_audit
from ..auth_deps import require_operator
from ..db import get_db
from ..errors import AppError
from ..schemas import NodeTemplateApply, NodeTemplateCreate, NodeTemplateUpdate
from ..security import AuthContext
from ..template_service import (
    apply_template,
    create_template,
    delete_template,
    list_templates,
    serialize,
    update_template,
)

router = APIRouter(prefix="/node-templates", tags=["node-templates"])


@router.get("")
def templates(db: Session = Depends(get_db), _context: AuthContext = Depends(require_operator)):
    return {"items": [serialize(row) for row in list_templates(db)]}


@router.post("", status_code=201)
def create_template_route(
    payload: NodeTemplateCreate,
    request: Request,
    db: Session = Depends(get_db),
    context: AuthContext = Depends(require_operator),
):
    if context.scope_groups is not None and payload.group_name not in context.scope_groups:
        raise AppError("auth.forbidden")
    row = create_template(db, payload=payload, actor_id=context.user_id)
    add_audit(
        db,
        actor=context,
        action_code="node.template_created",
        action_params={"name": row.name, "model": row.model, "group": row.group_name},
        target_type="template",
        target_id=row.id,
        request=request,
    )
    db.commit()
    return serialize(row)


@router.patch("/{template_id}")
def update_template_route(
    template_id: int,
    payload: NodeTemplateUpdate,
    request: Request,
    db: Session = Depends(get_db),
    context: AuthContext = Depends(require_operator),
):
    from ..models import NodeTemplate

    existing = db.get(NodeTemplate, template_id)
    if existing is None:
        raise AppError("app.not_found", params={"id": template_id})
    if context.scope_groups is not None:
        if existing.group_name not in context.scope_groups:
            raise AppError("app.not_found", params={"id": template_id})
        data = payload.model_dump(exclude_unset=True)
        if data.get("group_name") not in (None, *context.scope_groups):
            raise AppError("auth.forbidden")
    row = update_template(db, template_id, payload)
    add_audit(
        db,
        actor=context,
        action_code="node.template_updated",
        action_params={"name": row.name},
        target_type="template",
        target_id=row.id,
        request=request,
    )
    db.commit()
    return serialize(row)


@router.delete("/{template_id}", status_code=204)
def delete_template_route(
    template_id: int,
    request: Request,
    db: Session = Depends(get_db),
    context: AuthContext = Depends(require_operator),
):
    from ..models import NodeTemplate

    existing = db.get(NodeTemplate, template_id)
    if existing is None:
        raise AppError("app.not_found", params={"id": template_id})
    if context.scope_groups is not None and existing.group_name not in context.scope_groups:
        raise AppError("app.not_found", params={"id": template_id})
    delete_template(db, template_id)
    add_audit(
        db,
        actor=context,
        action_code="node.template_deleted",
        action_params={"template_id": template_id},
        target_type="template",
        target_id=template_id,
        request=request,
    )
    db.commit()
    return Response(status_code=204)


@router.post("/{template_id}/apply", status_code=201)
def apply_template_route(
    template_id: int,
    payload: NodeTemplateApply,
    request: Request,
    db: Session = Depends(get_db),
    context: AuthContext = Depends(require_operator),
):
    result = apply_template(
        db,
        template_id=template_id,
        payload=payload,
        actor=context,
        request=request,
    )
    add_audit(
        db,
        actor=context,
        action_code="node.template_applied",
        action_params={"template_id": template_id, "name": payload.name},
        target_type="template",
        target_id=template_id,
        request=request,
    )
    db.commit()
    return result
