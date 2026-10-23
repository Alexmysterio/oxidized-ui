from __future__ import annotations

import re
from typing import Any

from sqlalchemy.orm import Session

from .config_service import applied_config
from .diffing import build_diff
from .errors import AppError
from .models import Node
from .oxidized import OxidizedClient, client_for
from .timeutil import to_iso

OID_RE = re.compile(r"^[A-Za-z0-9._-]{4,128}$")


def supports_versions(db: Session) -> bool:
    config = applied_config(db)
    output = config.get("output") if isinstance(config, dict) else None
    default = output.get("default") if isinstance(output, dict) else None
    return default in {"git", "gitcrypt"}


def validate_oid(oid: str) -> str:
    if not OID_RE.fullmatch(oid):
        raise AppError("validation.invalid_format", params={"field": "oid"})
    return oid


def _live_group(client: OxidizedClient, node: Node) -> str | None:
    live = client.list_nodes()
    match = next((item for item in live if item.name == node.name), None)
    if match is None:
        raise AppError("oxidized.bad_response", params={"reason": "node_not_loaded"})
    # oxidized-web reports the implicit group as "default". Its version and
    # fetch endpoints only accept a real group, so sending "default" makes
    # them return [] / "node not found" even though the node exists.
    if not match.group or match.group == "default":
        return None
    return match.group


def list_versions(db: Session, node: Node) -> dict[str, Any]:
    if not supports_versions(db):
        return {"available": False, "reason": "output_unsupported", "versions": []}
    client = client_for(db)
    group = _live_group(client, node)
    versions = client.versions(node.name, group)
    return {
        "available": True,
        "reason": None,
        "versions": [
            {
                "oid": version.oid,
                "time": to_iso(version.time),
                "author": version.author,
                "message": version.message,
            }
            for version in versions
        ],
    }


def current_config(db: Session, node: Node) -> str:
    client = client_for(db)
    group = _live_group(client, node)
    return client.fetch_config(node.name, group)


def version_content(db: Session, node: Node, oid: str) -> dict[str, Any]:
    validate_oid(oid)
    if not supports_versions(db):
        raise AppError("oxidized.output_unsupported")
    client = client_for(db)
    group = _live_group(client, node)
    versions = client.versions(node.name, group)
    match = next((item for item in versions if item.oid == oid), None)
    if match is None:
        raise AppError("oxidized.bad_response", params={"reason": "version_not_found"})
    content = client.version_content(node.name, group, oid, epoch=int(match.time.timestamp()) if match.time else 0)
    return {
        "node_id": node.id,
        "oid": oid,
        "time": to_iso(match.time),
        "content": content,
    }


def version_diff(
    db: Session,
    node: Node,
    from_oid: str,
    to_oid: str,
) -> dict[str, Any]:
    validate_oid(from_oid)
    validate_oid(to_oid)
    if not supports_versions(db):
        raise AppError("oxidized.output_unsupported")
    client = client_for(db)
    group = _live_group(client, node)
    versions = client.versions(node.name, group)
    by_oid = {version.oid: version for version in versions}
    if from_oid not in by_oid or to_oid not in by_oid:
        raise AppError("oxidized.bad_response", params={"reason": "version_not_found"})
    old = client.version_content(node.name, group, from_oid)
    new = client.version_content(node.name, group, to_oid)
    diff = build_diff(old, new)
    return {
        "node_id": node.id,
        "from": {
            "oid": from_oid,
            "time": to_iso(by_oid[from_oid].time),
        },
        "to": {
            "oid": to_oid,
            "time": to_iso(by_oid[to_oid].time),
        },
        **diff,
    }


def content_for_download(db: Session, node: Node, oid: str | None) -> tuple[str, str]:
    if oid:
        payload = version_content(db, node, oid)
        content = payload["content"]
        suffix = oid
    else:
        content = current_config(db, node)
        suffix = "current"
    filename = f"{node.name}-{suffix}.txt"
    return filename, content
