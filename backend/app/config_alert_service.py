from __future__ import annotations

import hashlib
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .errors import AppError
from .maintenance_service import scoped_node_ids
from .models import Node, NodeConfigState
from .notifications import notify_config_change
from .oxidized import OxidizedNode
from .oxidized import client_for as oxidized_client_for
from .timeutil import ensure_utc, utcnow

logger = logging.getLogger("oxidized_ui.config_alerts")


def normalize_config(text: str) -> str:
    lines = [line.rstrip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines) + "\n"


def content_digest(text: str) -> str:
    return hashlib.sha256(normalize_config(text).encode("utf-8")).hexdigest()


def detect_config_changes(db: Session, live_nodes: list[OxidizedNode]) -> int:
    if not live_nodes:
        return 0
    by_name = {node.name: node for node in db.scalars(select(Node)).all()}
    maintenance = scoped_node_ids(db)
    client = oxidized_client_for(db)
    now = utcnow()
    changed = 0
    for live in live_nodes:
        node = by_name.get(live.name)
        if node is None or live.mtime is None:
            continue
        mtime = ensure_utc(live.mtime)
        group = None if not live.group or live.group == "default" else live.group
        state = db.get(NodeConfigState, node.id)
        if state is None:
            digest = None
            try:
                digest = content_digest(client.fetch_config(live.name, group))
            except AppError:
                digest = None
            except Exception:  # noqa: BLE001 - detection must never break the poller
                logger.warning("Could not read configuration for %s", node.name)
            db.add(
                NodeConfigState(
                    node_id=node.id,
                    last_mtime=mtime,
                    content_sha256=digest,
                    last_checked_at=now,
                )
            )
            continue
        if ensure_utc(state.last_mtime) == mtime:
            continue
        try:
            content = client.fetch_config(live.name, group)
        except AppError:
            continue
        except Exception:  # noqa: BLE001 - detection must never break the poller
            logger.warning("Could not read configuration for %s", node.name)
            continue
        digest = content_digest(content)
        if state.content_sha256 is not None and digest != state.content_sha256:
            state.last_changed_at = now
            state.content_sha256 = digest
            state.last_mtime = mtime
            state.last_checked_at = now
            if node.id not in maintenance and notify_config_change(db, node.name, now.isoformat()):
                changed += 1
            continue
        state.content_sha256 = digest
        state.last_mtime = mtime
        state.last_checked_at = now
    db.commit()
    return changed


def state_public(db: Session, node_id: int) -> dict[str, Any] | None:
    state = db.get(NodeConfigState, node_id)
    if state is None:
        return None
    return {
        "last_changed_at": state.last_changed_at.isoformat() if state.last_changed_at else None,
        "last_checked_at": state.last_checked_at.isoformat() if state.last_checked_at else None,
    }
