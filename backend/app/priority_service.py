from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .errors import AppError
from .models import JobPriorityRule, Node

SCOPE_TYPES = ("group", "tag")
DEFAULT_PRIORITY = 5


def serialize_rule(row: JobPriorityRule) -> dict[str, Any]:
    return {
        "id": row.id,
        "scope_type": row.scope_type,
        "scope_key": row.scope_key,
        "scope_value": row.scope_value,
        "priority": row.priority,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def list_rules(db: Session) -> list[JobPriorityRule]:
    return list(db.scalars(select(JobPriorityRule).order_by(JobPriorityRule.priority, JobPriorityRule.id)).all())


def create_rule(
    db: Session,
    *,
    scope_type: str,
    scope_key: str,
    scope_value: str | None,
    priority: int,
) -> JobPriorityRule:
    if scope_type not in SCOPE_TYPES:
        raise AppError("validation.invalid_choice", params={"field": "scope_type"})
    key = (scope_key or "").strip()
    if not key:
        raise AppError("validation.required", params={"field": "scope_key"})
    if priority < 1 or priority > 10:
        raise AppError("validation.range", params={"field": "priority", "min": 1, "max": 10})
    value = (scope_value or "").strip() or None
    if scope_type == "tag" and value is None:
        raise AppError("validation.required", params={"field": "scope_value"})
    existing = db.scalar(
        select(JobPriorityRule).where(
            JobPriorityRule.scope_type == scope_type,
            JobPriorityRule.scope_key == key,
            JobPriorityRule.scope_value == value,
        )
    )
    if existing is not None:
        raise AppError("validation.duplicate", params={"field": "scope_key"})
    row = JobPriorityRule(scope_type=scope_type, scope_key=key, scope_value=value, priority=priority)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def delete_rule(db: Session, rule_id: int) -> None:
    row = db.get(JobPriorityRule, rule_id)
    if row is None:
        raise AppError("app.not_found", params={"id": rule_id})
    db.delete(row)
    db.commit()


def _matches(node: Node, rule: JobPriorityRule) -> bool:
    if rule.scope_type == "group":
        return bool(node.group_name) and node.group_name.casefold() == rule.scope_key.casefold()
    if rule.scope_type == "tag":
        tags = node.tags if isinstance(node.tags, dict) else {}
        value = tags.get(rule.scope_key)
        return value is not None and str(value).casefold() == (rule.scope_value or "").casefold()
    return False


def priority_for(
    db: Session,
    *,
    node_id: int | None = None,
    payload: dict[str, Any] | None = None,
) -> int:
    rules = list_rules(db)
    if not rules:
        return DEFAULT_PRIORITY
    nodes: list[Node] = []
    if node_id is not None:
        node = db.get(Node, node_id)
        if node is not None:
            nodes.append(node)
    elif isinstance(payload, dict):
        ids: list[int] = []
        for value in payload.get("node_ids", []) or []:
            try:
                ids.append(int(value))
            except (TypeError, ValueError):
                continue
        if ids:
            nodes = list(db.scalars(select(Node).where(Node.id.in_(ids))).all())
    if not nodes:
        return DEFAULT_PRIORITY
    best = DEFAULT_PRIORITY
    for node in nodes:
        for rule in rules:
            if _matches(node, rule):
                best = min(best, rule.priority)
    return best
