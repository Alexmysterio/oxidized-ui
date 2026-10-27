from __future__ import annotations

import base64
import hashlib
import ipaddress
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from fastapi import Request
from sqlalchemy.orm import Session

from .audit import add_audit
from .errors import AppError
from .models import Node
from .security import AuthContext
from .settings import settings

HOSTNAME_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?$")
KEY_TYPES = ("ssh-", "ecdsa-", "sk-")


def known_hosts_path() -> Path:
    return Path(settings.oxidized_config_dir) / ".ssh" / "known_hosts"


def _validate_address(value: str | None) -> str:
    address = (value or "").strip()
    if not address or address.startswith("-"):
        raise AppError("node.invalid_address")
    try:
        ipaddress.ip_address(address)
        return address
    except ValueError:
        if not HOSTNAME_RE.fullmatch(address):
            raise AppError("node.invalid_address") from None
        return address


def _scan(address: str, port: int) -> list[str]:
    from .net_safety import ensure_safe_target

    ensure_safe_target(address, port)
    try:
        result = subprocess.run(
            ["ssh-keyscan", "-T", "5", "-p", str(port), address],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        raise AppError("node.host_key_unreachable", params={"address": address, "port": port}) from None
    hosts = {address, f"[{address}]:{port}"}
    lines: list[str] = []
    for raw in result.stdout.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 3 or parts[0] not in hosts or not parts[1].startswith(KEY_TYPES):
            continue
        lines.append(f"{parts[0]} {parts[1]} {parts[2]}")
    if not lines:
        raise AppError("node.host_key_unreachable", params={"address": address, "port": port})
    return list(dict.fromkeys(lines))


def _fingerprints(lines: list[str]) -> list[str]:
    result: list[str] = []
    for line in lines:
        parts = line.split()
        if len(parts) < 3:
            continue
        try:
            digest = hashlib.sha256(base64.b64decode(parts[2], validate=True)).digest()
        except (ValueError, TypeError):
            raise AppError("node.host_key_invalid") from None
        fingerprint = "SHA256:" + base64.b64encode(digest).decode().rstrip("=")
        if fingerprint not in result:
            result.append(fingerprint)
    return result


def _host_alias_matches(host_field: str, address: str) -> bool:
    for alias in host_field.split(","):
        alias = alias.strip()
        if alias.startswith("[") and "]" in alias:
            alias = alias[1 : alias.index("]")]
        if alias == address:
            return True
    return False


def _write_known_hosts(address: str, lines: list[str]) -> None:
    target = known_hosts_path()
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        os.chmod(target.parent, 0o700)
    except OSError:
        pass
    existing: list[str] = []
    if target.exists():
        existing = target.read_text(encoding="utf-8").splitlines()
    kept = [line for line in existing if line.strip() and not _host_alias_matches(line.split()[0], address)]
    content = "\n".join([*kept, *lines]).rstrip("\n") + "\n"
    fd, temporary = tempfile.mkstemp(prefix=".known_hosts-", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def trust_host_key(
    db: Session,
    node: Node,
    *,
    actor: AuthContext,
    request: Request | None = None,
) -> dict[str, Any]:
    input_parts = {part.strip() for part in (node.input or "").split(",") if part.strip()}
    if input_parts and not input_parts.intersection({"ssh", "scp"}):
        raise AppError("node.host_key_not_ssh", params={"input": node.input})
    address = _validate_address(node.address)
    port = int(node.port or 22)
    if port < 1 or port > 65535:
        raise AppError("node.invalid_port")
    lines = _scan(address, port)
    fingerprints = _fingerprints(lines)
    _write_known_hosts(address, lines)
    add_audit(
        db,
        actor=actor,
        action_code="node.host_key_trusted",
        action_params={
            "name": node.name,
            "address": address,
            "port": port,
            "fingerprints": fingerprints,
        },
        target_type="node",
        target_id=node.id,
        request=request,
    )
    db.commit()
    return {
        "address": address,
        "port": port,
        "fingerprints": fingerprints,
        "key_types": [line.split()[1] for line in lines],
    }
