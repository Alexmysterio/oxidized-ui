from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from .config_service import applied_config
from .docker_api import client_for
from .models import Node
from .settings import settings

JOB_ERROR_RE = re.compile(
    r"Job '(?P<job>[^']+)'\]\s+Oxidized::Node -- (?P<address>\S+) raised "
    r"(?P<class>[\w:]+) with msg \"(?P<message>.*)\""
)
AUTH_USER_RE = re.compile(r"for user ([^@\s]+)@")
CRASH_HEADER_RE = re.compile(r"^(?P<message>.*?)\s*\[(?P<class>[\w:]+)\]$")
MAX_CRASH_BYTES = 200_000
MAX_BACKTRACE_LINES = 40


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
    if "nomethoderror" in lowered or "creating crashfile" in lowered:
        return "node.crash", {"class": error_class.rsplit("::", 1)[-1]}
    return "node.connection_error", {"class": error_class.rsplit("::", 1)[-1]}


def _timestamp(value: str | None) -> str | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.isoformat(timespec="milliseconds").replace("+00:00", "Z")
    except ValueError:
        return value


def _crash_directory(db: Session) -> tuple[Path, bool]:
    try:
        config = applied_config(db)
    except Exception:  # noqa: BLE001 - on-demand diagnostics must never fail
        config = {}
    crash = config.get("crash") if isinstance(config.get("crash"), dict) else {}
    raw = str(crash.get("directory") or "~/.config/oxidized/crashes")
    raw = raw.replace("~/.config/oxidized", str(settings.oxidized_config_dir), 1)
    path = Path(raw)
    if not path.is_absolute():
        path = settings.oxidized_config_dir / path
    return path, bool(crash.get("hostnames"))


def _read_crash(path: Path) -> dict[str, Any] | None:
    try:
        if path.stat().st_size > MAX_CRASH_BYTES:
            return None
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    lines = [line.rstrip() for line in content.splitlines()]
    if len(lines) < 2:
        return None
    at = lines[0].strip() or None
    header = CRASH_HEADER_RE.match(lines[1].strip())
    message = header.group("message") if header else lines[1].strip()
    error_class = header.group("class") if header else None
    backtrace = [
        line.strip()
        for line in lines[2:]
        if line.strip() and not set(line.strip()) <= {"-"}
    ]
    return {
        "at": at,
        "message": message,
        "error_class": error_class,
        "backtrace": backtrace[:MAX_BACKTRACE_LINES],
    }


def _crash_detail(db: Session, node: Node) -> dict[str, Any] | None:
    directory, hostnames = _crash_directory(db)
    names = [node.name, node.address] if hostnames else [node.address, node.name]
    candidates = [directory / name for name in names if name]
    existing = []
    for candidate in candidates:
        try:
            existing.append((candidate.stat().st_mtime, candidate))
        except OSError:
            continue
    if not existing:
        return None
    existing.sort(reverse=True)
    return _read_crash(existing[0][1])


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
        crash = (
            _crash_detail(db, node)
            if code == "node.crash" or "crash" in match.group("message").casefold()
            else None
        )
        return {
            "code": code,
            "params": params,
            "error_class": match.group("class"),
            "at": _timestamp(line.timestamp),
            "crash": crash,
        }
    return None
