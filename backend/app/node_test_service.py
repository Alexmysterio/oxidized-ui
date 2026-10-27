from __future__ import annotations

import re
import socket
import time
from typing import Any

import paramiko
from sqlalchemy.orm import Session

from .catalog import models as catalog_models
from .config_service import applied_config, applied_groups
from .crypto import decrypt_optional
from .models import Node
from .net_safety import ensure_safe_target
from .ping_service import ping_host
from .settings import settings

ANSI_ESCAPE = re.compile(r"\x1B(?:\[[0-?]*[ -/]*[@-~]|[@-_])")


def test_connection(db: Session, node: Node) -> dict[str, Any]:
    result: dict[str, Any] = {
        "ping": False,
        "ping_rtt_ms": None,
        "ping_message": None,
        "tcp": False,
        "ssh": False,
        "authenticated": False,
        "model_known": node.model in set(catalog_models()),
        "prompt": None,
        "prompt_matches": False,
        "message": None,
    }
    if not node.address:
        result["message"] = "missing_address"
        return result
    ensure_safe_target(node.address, int(node.port or 22))
    ping = ping_host(node.address)
    result["ping"] = ping["reachable"]
    result["ping_rtt_ms"] = ping["rtt_ms"]
    result["ping_message"] = ping["message"]
    port = int(node.port or 22)
    try:
        with socket.create_connection((node.address, port), timeout=5):
            result["tcp"] = True
    except OSError as exc:
        result["message"] = f"tcp: {exc.__class__.__name__}"
        return result

    config = applied_config(db)
    input_cfg = config.get("input") if isinstance(config, dict) else {}
    default_input = str(input_cfg.get("default") or "") if isinstance(input_cfg, dict) else ""
    effective_input = node.input or default_input
    parts = {part.strip() for part in effective_input.split(",") if part.strip()}
    if "ssh" not in parts and "scp" not in parts:
        result["message"] = "input_is_not_ssh"
        return result

    group = applied_groups(db).get(node.group_name or "") or {}
    override = (group.get("models") or {}).get(node.model) or {}
    username = node.username or override.get("username") or group.get("username")
    password = (
        decrypt_optional(node.password_ciphertext)
        or override.get("password")
        or group.get("password")
    )
    if not username or not password:
        result["message"] = "missing_credentials"
        return result

    client = paramiko.SSHClient()
    known_hosts = settings.oxidized_config_dir / ".ssh" / "known_hosts"
    if known_hosts.exists():
        client.load_host_keys(str(known_hosts))
    client.set_missing_host_key_policy(paramiko.RejectPolicy())
    try:
        client.connect(
            node.address,
            port=port,
            username=str(username),
            password=str(password),
            timeout=8,
            banner_timeout=8,
            auth_timeout=8,
            allow_agent=False,
            look_for_keys=False,
        )
        result["ssh"] = True
        result["authenticated"] = True
        shell = client.invoke_shell()
        time.sleep(0.8)
        shell.send("\n")
        time.sleep(0.8)
        chunks: list[str] = []
        while shell.recv_ready():
            chunks.append(shell.recv(4096).decode("utf-8", errors="replace"))
        text = ANSI_ESCAPE.sub("", "".join(chunks)).replace("\r", "")
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        prompt = lines[-1] if lines else None
        result["prompt"] = prompt[:200] if prompt else None
        if node.prompt and prompt:
            try:
                result["prompt_matches"] = bool(re.search(node.prompt, prompt))
            except re.error:
                result["prompt_matches"] = False
        else:
            result["prompt_matches"] = bool(prompt and re.search(r"[#>]\s*$", prompt))
        result["message"] = "ok"
        shell.close()
    except paramiko.AuthenticationException:
        result["message"] = "authentication_failed"
    except paramiko.SSHException as exc:
        message = str(exc)
        unknown = "known_hosts" in message or "not found in" in message
        result["message"] = "host_key_unknown" if unknown else f"ssh: {exc.__class__.__name__}"
    except (OSError, EOFError) as exc:
        result["message"] = f"ssh: {exc.__class__.__name__}"
    finally:
        client.close()
    return result
