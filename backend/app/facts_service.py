from __future__ import annotations

import logging
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .errors import AppError
from .jobs import Job, update_progress
from .models import Node, NodeFacts
from .version_service import current_config

logger = logging.getLogger("oxidized_ui.facts")

SERIAL_PATTERNS = (
    re.compile(r"(?im)^\s*(?:system\s+)?serial\s*(?:number|no\.?)?\s*[:=]?\s*([A-Za-z0-9._/-]{4,64})"),
    re.compile(r"(?im)^\s*processor\s+board\s+id\s+([A-Za-z0-9._/-]{4,64})"),
    re.compile(r"(?im)^\s*chassis\s+serial\s+number\s*[:=]?\s*([A-Za-z0-9._/-]{4,64})"),
)
VERSION_PATTERNS = (
    re.compile(r"(?im)^.*?software\s+version\s*[:=]?\s*([A-Za-z0-9._()/-]{3,64})"),
    re.compile(r"(?im)^.*?\bversion\s+([A-Za-z0-9._()/-]{3,64})"),
)
UPTIME_PATTERNS = (
    re.compile(r"(?im)^.*?uptime\s+is\s+(.{2,200})$"),
    re.compile(r"(?im)^.*?uptime\s*[:=]\s*(.{2,200})$"),
)


def _first(patterns: tuple[re.Pattern[str], ...], text: str) -> str | None:
    for pattern in patterns:
        match = pattern.search(text)
        if match:
            value = match.group(1).strip().rstrip(",")
            if value:
                return value[:255]
    return None


def parse_facts(text: str) -> dict[str, str | None]:
    return {
        "serial": _first(SERIAL_PATTERNS, text),
        "os_version": _first(VERSION_PATTERNS, text),
        "uptime": _first(UPTIME_PATTERNS, text),
    }


def collect_node(db: Session, node: Node) -> dict[str, Any]:
    try:
        content = current_config(db, node)
    except AppError as exc:
        raise AppError("facts.collect_failed", params={"name": node.name, "reason": exc.code}) from exc
    parsed = parse_facts(content)
    row = db.get(NodeFacts, node.id)
    if row is None:
        row = NodeFacts(node_id=node.id)
        db.add(row)
    row.serial = parsed["serial"]
    row.os_version = parsed["os_version"]
    row.uptime = parsed["uptime"]
    from .timeutil import utcnow

    row.collected_at = utcnow()
    db.commit()
    return {"node_id": node.id, "name": node.name, **parsed}


def run_facts_job(db: Session, job: Job) -> dict[str, Any]:
    nodes = list(db.scalars(select(Node).order_by(Node.name)).all())
    requested = [int(value) for value in job.payload.get("node_ids", []) or []]
    if requested:
        wanted = set(requested)
        nodes = [node for node in nodes if node.id in wanted]
    results: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for index, node in enumerate(nodes, start=1):
        try:
            results.append(collect_node(db, node))
        except AppError as exc:
            failures.append({"id": node.id, "name": node.name, "code": exc.code})
        update_progress(db, job, done=index, total=len(nodes))
    return {"requested": len(nodes), "collected": len(results), "failed": failures, "ok": not failures}


def facts_public(db: Session, node_id: int) -> dict[str, Any] | None:
    row = db.get(NodeFacts, node_id)
    if row is None:
        return None
    return {
        "serial": row.serial,
        "os_version": row.os_version,
        "uptime": row.uptime,
        "collected_at": row.collected_at.isoformat() if row.collected_at else None,
    }


def search_facts(db: Session, query: str, *, allowed_groups: list[str] | None = None) -> list[dict[str, Any]]:
    needle = f"%{query.strip()}%"
    if not query.strip():
        return []
    rows = db.execute(
        select(Node, NodeFacts)
        .join(NodeFacts, NodeFacts.node_id == Node.id)
        .where(
            NodeFacts.serial.ilike(needle)
            | NodeFacts.os_version.ilike(needle)
            | NodeFacts.uptime.ilike(needle)
        )
        .limit(10)
    ).all()
    result: list[dict[str, Any]] = []
    for node, facts in rows:
        if allowed_groups is not None and node.group_name not in allowed_groups:
            continue
        result.append(
            {
                "id": node.id,
                "name": node.name,
                "address": node.address,
                "model": node.model,
                "group_name": node.group_name,
                "serial": facts.serial,
                "os_version": facts.os_version,
            }
        )
    return result
