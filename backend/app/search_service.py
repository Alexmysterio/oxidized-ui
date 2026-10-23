from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config_service import applied_groups
from .errors import AppError
from .models import Node
from .oxidized import client_for


def global_search(db: Session, query: str, role: str) -> dict[str, Any]:
    needle = query.strip()
    if not needle:
        return {"nodes": [], "groups": []}
    nodes = db.scalars(
        select(Node)
        .where(Node.name.ilike(f"%{needle}%") | Node.address.ilike(f"%{needle}%") | Node.model.ilike(f"%{needle}%"))
        .order_by(Node.name)
        .limit(10)
    ).all()
    groups = [{"name": name} for name in sorted(applied_groups(db)) if needle.casefold() in name.casefold()][:10]
    return {
        "nodes": [
            {
                "id": node.id,
                "name": node.name,
                "address": node.address,
                "model": node.model,
                "group_name": node.group_name,
            }
            for node in nodes
        ],
        "groups": groups,
    }


def config_search(db: Session, query: str) -> list[dict[str, Any]]:
    text = query.strip()
    if not text or len(text) > 200:
        raise AppError("search.query_invalid")
    try:
        matches = client_for(db).search_configs(text)
    except AppError as exc:
        if exc.code in {"oxidized.unavailable", "oxidized.timeout"}:
            raise
        raise AppError("search.upstream_failed", params={"reason": exc.code}) from exc
    if not matches:
        return []
    by_name = {node.name: node for node in db.scalars(select(Node)).all()}
    result: list[dict[str, Any]] = []
    for match in matches[:100]:
        node = by_name.get(match["name"])
        if node is None:
            continue
        result.append(
            {
                "node_id": node.id,
                "name": node.name,
                "full_name": match.get("full_name") or node.name,
                "group_name": node.group_name,
                "model": node.model,
            }
        )
    return result
