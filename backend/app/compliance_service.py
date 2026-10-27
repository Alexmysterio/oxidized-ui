from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .diffing import build_diff
from .errors import AppError
from .models import ConfigTemplate, Node
from .node_service import get_node
from .scope_service import scoped_groups
from .security import AuthContext
from .version_service import current_config

SCOPE_TYPES = ("global", "group", "model")


def serialize_template(row: ConfigTemplate) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "scope_type": row.scope_type,
        "scope_value": row.scope_value,
        "content": row.content,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def list_templates(db: Session) -> list[ConfigTemplate]:
    return list(db.scalars(select(ConfigTemplate).order_by(ConfigTemplate.name)).all())


def create_template(
    db: Session,
    *,
    name: str,
    scope_type: str,
    scope_value: str | None,
    content: str,
    actor_id: int,
) -> ConfigTemplate:
    name = name.strip()
    if not name:
        raise AppError("validation.required", params={"field": "name"})
    if db.scalar(select(ConfigTemplate).where(ConfigTemplate.name == name)) is not None:
        raise AppError("validation.duplicate", params={"field": "name"})
    scope_type, scope_value = _validate_scope(scope_type, scope_value)
    if not content.strip():
        raise AppError("validation.required", params={"field": "content"})
    row = ConfigTemplate(
        name=name,
        scope_type=scope_type,
        scope_value=scope_value,
        content=content,
        created_by_id=actor_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update_template(db: Session, template_id: int, **values: Any) -> ConfigTemplate:
    row = db.get(ConfigTemplate, template_id)
    if row is None:
        raise AppError("app.not_found", params={"id": template_id})
    if "name" in values and values["name"] is not None:
        name = str(values["name"]).strip()
        if not name:
            raise AppError("validation.required", params={"field": "name"})
        existing = db.scalar(select(ConfigTemplate).where(ConfigTemplate.name == name))
        if existing is not None and existing.id != template_id:
            raise AppError("validation.duplicate", params={"field": "name"})
        row.name = name
    if "content" in values and values["content"] is not None:
        if not str(values["content"]).strip():
            raise AppError("validation.required", params={"field": "content"})
        row.content = values["content"]
    if "scope_type" in values and values["scope_type"] is not None:
        row.scope_type, row.scope_value = _validate_scope(
            values["scope_type"], values.get("scope_value")
        )
    elif "scope_value" in values and values["scope_value"] is not None:
        row.scope_type, row.scope_value = _validate_scope(row.scope_type, values["scope_value"])
    db.commit()
    db.refresh(row)
    return row


def delete_template(db: Session, template_id: int) -> None:
    row = db.get(ConfigTemplate, template_id)
    if row is None:
        raise AppError("app.not_found", params={"id": template_id})
    db.delete(row)
    db.commit()


def _validate_scope(scope_type: str, scope_value: str | None) -> tuple[str, str | None]:
    if scope_type not in SCOPE_TYPES:
        raise AppError("validation.invalid_choice", params={"field": "scope_type"})
    if scope_type == "global":
        return scope_type, None
    value = (scope_value or "").strip()
    if not value:
        raise AppError("validation.required", params={"field": "scope_value"})
    return scope_type, value


def template_for(db: Session, node: Node, templates: list[ConfigTemplate] | None = None) -> ConfigTemplate | None:
    rows = templates if templates is not None else list_templates(db)
    by_scope = {(row.scope_type, row.scope_value): row for row in rows}
    return (
        by_scope.get(("group", node.group_name))
        or by_scope.get(("model", node.model))
        or by_scope.get(("global", None))
    )


def _diff_stats(template: str, config: str) -> dict[str, Any]:
    diff = build_diff(template, config)
    stats = diff["stats"]
    return {
        "additions": int(stats["additions"]),
        "deletions": int(stats["deletions"]),
        "changed": int(stats["additions"]) + int(stats["deletions"]),
        "diff": diff,
    }


def report(
    db: Session,
    *,
    ctx: AuthContext,
    group_name: str | None = None,
    model: str | None = None,
    template_id: int | None = None,
    limit: int = 500,
) -> dict[str, Any]:
    templates = list_templates(db)
    selected = next((row for row in templates if row.id == template_id), None) if template_id else None
    scope = scoped_groups(ctx)
    query = select(Node).order_by(Node.name)
    if group_name:
        query = query.where(Node.group_name == group_name)
    if model:
        query = query.where(Node.model == model)
    nodes = [
        node
        for node in db.scalars(query).all()
        if scope is None or (node.group_name is not None and node.group_name in scope)
    ][: max(1, min(limit, 1000))]
    items: list[dict[str, Any]] = []
    summary = {"compliant": 0, "deviating": 0, "no_template": 0, "error": 0}
    for node in nodes:
        template = selected or template_for(db, node, templates)
        if template is None:
            summary["no_template"] += 1
            items.append(_item(node, None, "no_template"))
            continue
        try:
            config = current_config(db, node)
        except AppError:
            summary["error"] += 1
            items.append(_item(node, template, "error"))
            continue
        stats = _diff_stats(template.content, config)
        if stats["changed"] == 0:
            summary["compliant"] += 1
            items.append(_item(node, template, "compliant"))
        else:
            summary["deviating"] += 1
            items.append(_item(node, template, "deviating", stats))
    return {"items": items, "summary": summary, "total": len(items)}


def _item(
    node: Node,
    template: ConfigTemplate | None,
    status: str,
    stats: dict[str, Any] | None = None,
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "node_id": node.id,
        "name": node.name,
        "group_name": node.group_name,
        "model": node.model,
        "template_id": template.id if template else None,
        "template_name": template.name if template else None,
        "status": status,
        "additions": stats["additions"] if stats else 0,
        "deletions": stats["deletions"] if stats else 0,
    }
    return data


def node_report(
    db: Session,
    *,
    ctx: AuthContext,
    node_id: int,
    template_id: int | None = None,
) -> dict[str, Any]:
    node = get_node(db, node_id)
    scope = scoped_groups(ctx)
    if scope is not None and (node.group_name is None or node.group_name not in scope):
        raise AppError("node.not_found", params={"node_id": node_id})
    template = (
        db.get(ConfigTemplate, template_id) if template_id else template_for(db, node)
    )
    if template is None:
        raise AppError("compliance.template_missing")
    config = current_config(db, node)
    stats = _diff_stats(template.content, config)
    return {
        "node_id": node.id,
        "name": node.name,
        "template": serialize_template(template),
        "diff": stats["diff"],
        "additions": stats["additions"],
        "deletions": stats["deletions"],
        "compliant": stats["changed"] == 0,
    }
