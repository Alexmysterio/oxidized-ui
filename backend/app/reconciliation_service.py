from __future__ import annotations

from typing import Any

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config_service import applied_groups
from .errors import AppError
from .models import Node
from .node_service import create_node
from .oxidized import OxidizedNode
from .oxidized import client_for as oxidized_client_for
from .schemas import NodeCreate
from .security import AuthContext


def _scope_filter(nodes: list[dict[str, Any]], allowed_groups: list[str] | None) -> list[dict[str, Any]]:
    if allowed_groups is None:
        return nodes
    return [item for item in nodes if item.get("group_name") in allowed_groups]


def compare(db: Session, *, allowed_groups: list[str] | None = None) -> dict[str, Any]:
    live = oxidized_client_for(db).list_nodes()
    ui_nodes = {node.name.casefold(): node for node in db.scalars(select(Node)).all()}
    live_by_key = {node.name.casefold(): node for node in live}

    missing_in_ui: list[dict[str, Any]] = []
    for key, item in live_by_key.items():
        if key in ui_nodes or not item.name:
            continue
        missing_in_ui.append(
            {
                "name": item.name,
                "address": item.address,
                "group_name": item.group,
                "model": item.model,
            }
        )

    missing_in_oxidized: list[dict[str, Any]] = []
    drift: list[dict[str, Any]] = []
    for key, node in ui_nodes.items():
        item = live_by_key.get(key)
        if item is None:
            missing_in_oxidized.append(
                {"id": node.id, "name": node.name, "group_name": node.group_name, "model": node.model}
            )
            continue
        changes: dict[str, Any] = {}
        if (item.address or None) != (node.address or None):
            changes["address"] = {"ui": node.address, "oxidized": item.address}
        if (item.group or None) != (node.group_name or None):
            changes["group_name"] = {"ui": node.group_name, "oxidized": item.group}
        if (item.model or None) != (node.model or None):
            changes["model"] = {"ui": node.model, "oxidized": item.model}
        if changes:
            drift.append(
                {
                    "id": node.id,
                    "name": node.name,
                    "group_name": node.group_name,
                    "model": node.model,
                    "changes": changes,
                }
            )

    missing_in_ui = _scope_filter(missing_in_ui, allowed_groups)
    missing_in_oxidized = _scope_filter(missing_in_oxidized, allowed_groups)
    drift = _scope_filter(drift, allowed_groups)
    return {
        "missing_in_ui": missing_in_ui,
        "missing_in_oxidized": missing_in_oxidized,
        "drift": drift,
        "summary": {
            "missing_in_ui": len(missing_in_ui),
            "missing_in_oxidized": len(missing_in_oxidized),
            "drift": len(drift),
            "oxidized_nodes": len(live),
            "ui_nodes": len(ui_nodes),
        },
    }


def import_nodes(
    db: Session,
    *,
    names: list[str],
    actor: AuthContext,
    request: Request,
    allowed_groups: list[str] | None = None,
) -> dict[str, Any]:
    live = {node.name.casefold(): node for node in oxidized_client_for(db).list_nodes()}
    known_groups = set(applied_groups(db))
    existing = {node.name_key for node in db.scalars(select(Node)).all()}
    imported: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for raw_name in names[:200]:
        key = str(raw_name).strip().casefold()
        if not key or key in existing:
            errors.append({"name": raw_name, "code": "node.duplicate_name", "params": {"name": raw_name}})
            continue
        item: OxidizedNode | None = live.get(key)
        if item is None:
            errors.append({"name": raw_name, "code": "node.not_found", "params": {"name": raw_name}})
            continue
        if allowed_groups is not None and item.group not in allowed_groups:
            errors.append({"name": raw_name, "code": "auth.forbidden", "params": {}})
            continue
        if not item.model:
            errors.append({"name": raw_name, "code": "validation.required", "params": {"field": "model"}})
            continue
        group_name = item.group if item.group in known_groups else None
        try:
            result = create_node(
                db,
                payload=NodeCreate(
                    name=item.name,
                    address=item.address,
                    model=item.model,
                    group_name=group_name,
                ),
                actor=actor,
                request=request,
                previous_count=0,
            )
        except AppError as exc:
            errors.append({"name": item.name, "code": exc.code, "params": exc.params})
            continue
        imported.append({"id": result["node"]["id"], "name": result["node"]["name"]})
        existing.add(key)
    return {"imported": imported, "errors": errors}
