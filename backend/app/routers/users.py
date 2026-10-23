from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from ..auth_deps import require_admin
from ..db import get_db
from ..schemas import UserCreate, UserPasswordReset, UserUpdate
from ..security import AuthContext
from ..serializers import user_public
from ..user_service import (
    create_user,
    delete_user,
    get_user,
    list_users,
    reset_password,
    update_user,
)

router = APIRouter(prefix="/users", tags=["users"], dependencies=[Depends(require_admin)])


@router.get("")
def list_users_route(
    search: str | None = Query(default=None, max_length=64),
    role: Literal["admin", "operator", "viewer"] | None = None,
    is_active: bool | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
    _context: AuthContext = Depends(require_admin),
):
    return list_users(
        db,
        search=search,
        role=role,
        is_active=is_active,
        page=page,
        page_size=page_size,
    )


@router.post("", status_code=201)
def create_user_route(
    payload: UserCreate,
    request: Request,
    db: Session = Depends(get_db),
    context: AuthContext = Depends(require_admin),
):
    user = create_user(db, payload=payload, actor=context, request=request)
    return user_public(user)


@router.get("/{user_id}")
def get_user_route(
    user_id: int,
    db: Session = Depends(get_db),
    _context: AuthContext = Depends(require_admin),
):
    return user_public(get_user(db, user_id))


@router.patch("/{user_id}")
def update_user_route(
    user_id: int,
    payload: UserUpdate,
    request: Request,
    db: Session = Depends(get_db),
    context: AuthContext = Depends(require_admin),
):
    return user_public(update_user(db, user_id=user_id, payload=payload, actor=context, request=request))


@router.post("/{user_id}/password")
def reset_password_route(
    user_id: int,
    payload: UserPasswordReset,
    request: Request,
    db: Session = Depends(get_db),
    context: AuthContext = Depends(require_admin),
):
    reset_password(db, user_id=user_id, payload=payload, actor=context, request=request)
    return Response(status_code=204)


@router.delete("/{user_id}", status_code=204)
def delete_user_route(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    context: AuthContext = Depends(require_admin),
):
    delete_user(db, user_id=user_id, actor=context, request=request)
    return Response(status_code=204)
