from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from .. import config_service
from ..audit import add_audit
from ..auth_deps import require_operator
from ..db import get_db
from ..errors import AppError
from ..schemas import GroupCreate, GroupWrite, validate_group_name
from ..security import AuthContext

router = APIRouter(prefix="/groups", tags=["groups"])


@router.get("")
def list_groups(
    db: Session = Depends(get_db),
    context: AuthContext = Depends(require_operator),
):
    result = config_service.groups_list(db)
    if context.scope_groups is not None:
        allowed = set(context.scope_groups)
        result["groups"] = [row for row in result["groups"] if row.get("name") in allowed]
    return result


@router.get("/{name}")
def get_group(
    name: str,
    db: Session = Depends(get_db),
    context: AuthContext = Depends(require_operator),
):
    from ..scope_service import require_group

    validate_group_name(name)
    require_group(context, name)
    return config_service.groups_detail(db, name)


@router.post("", status_code=201)
def create_group(
    payload: GroupCreate,
    request: Request,
    expected_revision_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    context: AuthContext = Depends(require_operator),
):
    patch = payload.model_dump(exclude={"name"}, exclude_unset=True)
    if context.scope_groups is not None:
        raise AppError("auth.forbidden")
    revision = config_service.group_write_config(
        db,
        name=payload.name,
        patch=patch,
        actor_id=context.user_id,
        expected_revision_id=expected_revision_id,
    )
    add_audit(
        db,
        actor=context,
        action_code="group.created",
        action_params={"name": payload.name, "revision_id": revision.id},
        target_type="config",
        target_id=revision.id,
        request=request,
    )
    db.commit()
    return {
        "revision_id": revision.id,
        "requires_admin_apply": True,
        "group": config_service.groups_detail(db, payload.name),
    }


@router.patch("/{name}")
def update_group(
    name: str,
    payload: GroupWrite,
    request: Request,
    expected_revision_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    context: AuthContext = Depends(require_operator),
):
    validate_group_name(name)
    from ..scope_service import require_group

    require_group(context, name)
    patch = payload.model_dump(exclude_unset=True)
    revision = config_service.group_write_config(
        db,
        name=name,
        patch=patch,
        actor_id=context.user_id,
        expected_revision_id=expected_revision_id,
    )
    add_audit(
        db,
        actor=context,
        action_code="group.updated",
        action_params={"name": name, "revision_id": revision.id},
        target_type="config",
        target_id=revision.id,
        request=request,
    )
    db.commit()
    return {
        "revision_id": revision.id,
        "requires_admin_apply": True,
        "group": config_service.groups_detail(db, name),
    }


@router.delete("/{name}", status_code=204)
def delete_group(
    name: str,
    request: Request,
    expected_revision_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    context: AuthContext = Depends(require_operator),
):
    validate_group_name(name)
    from ..scope_service import require_group

    require_group(context, name)
    revision = config_service.group_delete_config(
        db,
        name=name,
        actor_id=context.user_id,
        expected_revision_id=expected_revision_id,
    )
    add_audit(
        db,
        actor=context,
        action_code="group.deleted",
        action_params={"name": name, "revision_id": revision.id},
        target_type="config",
        target_id=revision.id,
        request=request,
    )
    db.commit()
    return Response(status_code=204)
