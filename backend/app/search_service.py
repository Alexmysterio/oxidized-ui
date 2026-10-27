from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config_service import applied_groups
from .errors import AppError
from .models import Node, NodeFacts
from .oxidized import client_for


def global_search(
    db: Session, query: str, role: str, allowed_groups: list[str] | None = None
) -> dict[str, Any]:
    needle = query.strip()
    if not needle:
        return {"nodes": [], "groups": []}
    criteria = (
        Node.name.ilike(f"%{needle}%")
        | Node.address.ilike(f"%{needle}%")
        | Node.model.ilike(f"%{needle}%")
    )
    statement = select(Node).where(criteria)
    if allowed_groups is not None:
        statement = statement.where(Node.group_name.in_(allowed_groups))
    nodes = db.scalars(statement.order_by(Node.name).limit(10)).all()
    fact_statement = (
        select(Node)
        .join(NodeFacts, NodeFacts.node_id == Node.id)
        .where(
            NodeFacts.serial.ilike(f"%{needle}%")
            | NodeFacts.os_version.ilike(f"%{needle}%")
            | NodeFacts.uptime.ilike(f"%{needle}%")
        )
        .limit(10)
    )
    if allowed_groups is not None:
        fact_statement = fact_statement.where(Node.group_name.in_(allowed_groups))
    merged = {node.id: node for node in nodes}
    for node in db.scalars(fact_statement).all():
        merged[node.id] = node
    nodes = sorted(merged.values(), key=lambda node: node.name)[:10]
    groups = [
        {"name": name}
        for name in sorted(applied_groups(db))
        if needle.casefold() in name.casefold() and (allowed_groups is None or name in allowed_groups)
    ][:10]
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


def config_search(db: Session, query: str, *, allowed_groups: list[str] | None = None) -> list[dict[str, Any]]:
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
        if allowed_groups is not None and node.group_name not in allowed_groups:
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
