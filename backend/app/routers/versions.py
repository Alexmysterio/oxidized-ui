from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from ..auth_deps import get_auth_context
from ..db import get_db
from ..scope_service import scoped_node
from ..security import AuthContext
from ..version_service import (
    content_for_download,
    current_config,
    list_versions,
    version_content,
    version_diff,
)

router = APIRouter(prefix="/nodes", tags=["versions"])


@router.get("/{node_id}/config")
def node_current_config(
    node_id: int,
    db: Session = Depends(get_db),
    context: AuthContext = Depends(get_auth_context),
):
    node = scoped_node(db, context, node_id)
    return Response(content=current_config(db, node), media_type="text/plain; charset=utf-8")


@router.get("/{node_id}/versions")
def node_versions(
    node_id: int,
    db: Session = Depends(get_db),
    context: AuthContext = Depends(get_auth_context),
):
    node = scoped_node(db, context, node_id)
    return list_versions(db, node)


@router.get("/{node_id}/versions/{oid}")
def node_version_content(
    node_id: int,
    oid: str,
    db: Session = Depends(get_db),
    context: AuthContext = Depends(get_auth_context),
):
    node = scoped_node(db, context, node_id)
    return version_content(db, node, oid)


@router.get("/{node_id}/diff")
def node_diff(
    node_id: int,
    from_oid: str = Query(min_length=4, max_length=128),
    to_oid: str = Query(min_length=4, max_length=128),
    db: Session = Depends(get_db),
    context: AuthContext = Depends(get_auth_context),
):
    node = scoped_node(db, context, node_id)
    return version_diff(db, node, from_oid, to_oid)


@router.get("/{node_id}/download")
def node_download(
    node_id: int,
    oid: str | None = Query(default=None, min_length=4, max_length=128),
    db: Session = Depends(get_db),
    context: AuthContext = Depends(get_auth_context),
):
    node = scoped_node(db, context, node_id)
    filename, content = content_for_download(db, node, oid)
    return Response(
        content=content,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
