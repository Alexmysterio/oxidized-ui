from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth_deps import require_admin
from ..db import get_db
from ..errors import AppError
from ..models import AuditLog
from ..security import AuthContext
from ..serializers import audit_public
from ..timeutil import parse_iso

router = APIRouter(prefix="/audit", tags=["audit"])


def _parse_filter(value: str | None, field: str):  # noqa: ANN001
    if not value:
        return None
    parsed = parse_iso(value)
    if parsed is None:
        raise AppError("validation.invalid_format", params={"field": field})
    return parsed


@router.get("")
def list_audit(
    actor: str | None = Query(default=None, max_length=64),
    action: str | None = Query(default=None, max_length=128),
    target_type: str | None = Query(default=None, max_length=32),
    target_id: str | None = Query(default=None, max_length=64),
    from_: str | None = Query(default=None, alias="from", max_length=64),
    to: str | None = Query(default=None, max_length=64),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
    _context: AuthContext = Depends(require_admin),
):
    from_dt = _parse_filter(from_, "from")
    to_dt = _parse_filter(to, "to")
    if from_dt and to_dt and (to_dt - from_dt).total_seconds() > 366 * 86400:
        raise AppError("validation.max", params={"field": "range", "max": "366 days"})
    conditions = []
    if actor:
        conditions.append(AuditLog.actor_username.ilike(f"%{actor}%"))
    if action:
        conditions.append(AuditLog.action_code == action)
    if target_type:
        conditions.append(AuditLog.target_type == target_type)
    if target_id:
        conditions.append(AuditLog.target_id == target_id)
    if from_dt:
        conditions.append(AuditLog.created_at >= from_dt)
    if to_dt:
        conditions.append(AuditLog.created_at <= to_dt)
    query = select(AuditLog)
    count_query = select(func.count(AuditLog.id))
    for condition in conditions:
        query = query.where(condition)
        count_query = count_query.where(condition)
    total = db.scalar(count_query) or 0
    rows = db.scalars(query.order_by(AuditLog.id.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return {
        "items": [audit_public(row) for row in rows],
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": (total + page_size - 1) // page_size,
    }


@router.get("/export.csv")
def export_audit(
    db: Session = Depends(get_db),
    _context: AuthContext = Depends(require_admin),
):
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["id", "created_at", "actor", "role", "action", "target_type", "target_id", "ip", "params"])
    rows = db.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(100_000)).all()
    for row in rows:
        writer.writerow(
            [
                row.id,
                row.created_at.isoformat() if row.created_at else "",
                row.actor_username,
                row.actor_role,
                row.action_code,
                row.target_type or "",
                row.target_id or "",
                row.ip or "",
                str(row.action_params or {}),
            ]
        )
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="oxidized-audit.csv"'},
    )
