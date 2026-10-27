from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from ..audit import add_audit
from ..auth_deps import require_capability
from ..compliance_service import (
    create_template,
    delete_template,
    list_templates,
    node_report,
    report,
    serialize_template,
    update_template,
)
from ..db import get_db
from ..errors import AppError
from ..schemas import ConfigTemplateCreate, ConfigTemplateUpdate
from ..security import AuthContext

router = APIRouter(prefix="/compliance", tags=["compliance"])


@router.get("/templates")
def templates(
    db: Session = Depends(get_db),
    context: AuthContext = Depends(require_capability("compliance.read")),
):
    rows = list_templates(db)
    if context.scope_groups is not None:
        allowed = set(context.scope_groups)
        rows = [row for row in rows if row.scope_type == "group" and row.scope_value in allowed]
    return {"items": [serialize_template(row) for row in rows]}


@router.post("/templates", status_code=201)
def create_template_route(
    payload: ConfigTemplateCreate,
    request: Request,
    db: Session = Depends(get_db),
    context: AuthContext = Depends(require_capability("compliance.write")),
):
    if context.scope_groups is not None:
        if payload.scope_type != "group" or payload.scope_value not in context.scope_groups:
            raise AppError("auth.forbidden")
    row = create_template(
        db,
        name=payload.name,
        scope_type=payload.scope_type,
        scope_value=payload.scope_value,
        content=payload.content,
        actor_id=context.user_id,
    )
    add_audit(
        db,
        actor=context,
        action_code="compliance.template_created",
        action_params={"name": row.name, "scope_type": row.scope_type, "scope_value": row.scope_value},
        target_type="compliance",
        target_id=row.id,
        request=request,
    )
    db.commit()
    return serialize_template(row)


@router.patch("/templates/{template_id}")
def update_template_route(
    template_id: int,
    payload: ConfigTemplateUpdate,
    request: Request,
    db: Session = Depends(get_db),
    context: AuthContext = Depends(require_capability("compliance.write")),
):
    from ..models import ConfigTemplate
    from ..scope_service import ensure_compliance_template_visible

    existing = db.get(ConfigTemplate, template_id)
    if existing is None:
        raise AppError("app.not_found", params={"id": template_id})
    ensure_compliance_template_visible(context, existing)
    data = payload.model_dump(exclude_unset=True)
    if context.scope_groups is not None:
        scope_type = data.get("scope_type", existing.scope_type)
        scope_value = data.get("scope_value", existing.scope_value)
        if scope_type != "group" or scope_value not in context.scope_groups:
            raise AppError("auth.forbidden")
    row = update_template(db, template_id, **data)
    add_audit(
        db,
        actor=context,
        action_code="compliance.template_updated",
        action_params={"name": row.name},
        target_type="compliance",
        target_id=row.id,
        request=request,
    )
    db.commit()
    return serialize_template(row)


@router.delete("/templates/{template_id}", status_code=204)
def delete_template_route(
    template_id: int,
    request: Request,
    db: Session = Depends(get_db),
    context: AuthContext = Depends(require_capability("compliance.write")),
):
    from ..models import ConfigTemplate
    from ..scope_service import ensure_compliance_template_visible

    existing = db.get(ConfigTemplate, template_id)
    if existing is None:
        raise AppError("app.not_found", params={"id": template_id})
    ensure_compliance_template_visible(context, existing)
    delete_template(db, template_id)
    add_audit(
        db,
        actor=context,
        action_code="compliance.template_deleted",
        action_params={"template_id": template_id},
        target_type="compliance",
        target_id=template_id,
        request=request,
    )
    db.commit()
    return Response(status_code=204)


@router.get("/report")
def compliance_report(
    group: str | None = Query(default=None, max_length=128),
    model: str | None = Query(default=None, max_length=128),
    template_id: int | None = Query(default=None, ge=1),
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
    context: AuthContext = Depends(require_capability("compliance.read")),
):
    return report(
        db,
        ctx=context,
        group_name=group,
        model=model,
        template_id=template_id,
        limit=limit,
    )


@router.get("/report/{node_id}")
def compliance_node_report(
    node_id: int,
    template_id: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
    context: AuthContext = Depends(require_capability("compliance.read")),
):
    return node_report(db, ctx=context, node_id=node_id, template_id=template_id)
