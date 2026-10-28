from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from ..audit import add_audit
from ..auth_deps import get_auth_context, require_capability
from ..db import get_db
from ..errors import AppError
from ..schemas import GoldenVersionRequest
from ..scope_service import scoped_node
from ..security import AuthContext
from ..timeutil import to_iso, utcnow
from ..version_service import (
    content_for_download,
    current_config,
    list_versions,
    validate_oid,
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


@router.put("/{node_id}/golden")
def set_golden_version(
    node_id: int,
    payload: GoldenVersionRequest,
    request: Request,
    db: Session = Depends(get_db),
    context: AuthContext = Depends(require_capability("nodes.write")),
):
    node = scoped_node(db, context, node_id)
    oid = (payload.oid or "").strip() or None
    if oid is not None:
        validate_oid(oid)
        data = list_versions(db, node)
        if not data.get("available") or not any(item["oid"] == oid for item in data["versions"]):
            raise AppError("version.not_found", params={"oid": oid})
    node.golden_oid = oid
    node.golden_at = utcnow() if oid else None
    add_audit(
        db,
        actor=context,
        action_code="node.golden_pinned" if oid else "node.golden_unpinned",
        action_params={"name": node.name, "oid": oid},
        target_type="node",
        target_id=node.id,
        request=request,
    )
    db.commit()
    return {"golden_oid": oid, "golden_at": to_iso(node.golden_at)}


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
