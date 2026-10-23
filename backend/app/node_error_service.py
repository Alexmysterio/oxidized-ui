from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from .docker_api import client_for
from .models import Node

JOB_ERROR_RE = re.compile(
    r"Job '(?P<job>[^']+)'\]\s+Oxidized::Node -- (?P<address>\S+) raised "
    r"(?P<class>[\w:]+) with msg \"(?P<message>.*)\""
)
AUTH_USER_RE = re.compile(r"for user ([^@\s]+)@")


def _classify(error_class: str, message: str) -> tuple[str, dict[str, str]]:
    lowered = f"{error_class} {message}".casefold()
    if "authenticationfailed" in lowered:
        match = AUTH_USER_RE.search(message)
        return "node.auth_failed", {"user": match.group(1) if match else "?"}
    if "hostkeyunknown" in lowered:
        return "node.host_key_unknown", {}
    if "connectiontimeout" in lowered or "timeout" in lowered:
        return "node.connection_timeout", {}
    if "econnrefused" in lowered or "connection refused" in lowered:
        return "node.connection_refused", {}
    if "name or service not known" in lowered or "getaddrinfo" in lowered or "socketerror" in lowered:
        return "node.dns_error", {}
    return "node.connection_error", {"class": error_class.rsplit("::", 1)[-1]}


def _timestamp(value: str | None) -> str | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.isoformat(timespec="milliseconds").replace("+00:00", "Z")
    except ValueError:
        return value


def latest_error(db: Session, node: Node) -> dict[str, Any] | None:
    """Read the latest Oxidized node exception from the container log.

    Oxidized's HTTP API exposes only success/no_connection/never, so the useful
    reason lives in its log. This is deliberately on-demand: it runs for the
    node detail endpoint, not for every node in a list.
    """

    lines = client_for(db).log_snapshot(tail=2000)
    for line in reversed(lines):
        match = JOB_ERROR_RE.search(line.text)
        if match is None:
            continue
        if match.group("job") != node.name and match.group("address") != node.address:
            continue
        code, params = _classify(match.group("class"), match.group("message"))
        return {
            "code": code,
            "params": params,
            "error_class": match.group("class"),
            "at": _timestamp(line.timestamp),
        }
    return None
