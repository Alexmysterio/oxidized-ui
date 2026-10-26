from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from .config_service import applied_config
from .crypto import decrypt_optional
from .models import Node
from .serializers import node_vars

PROTOCOL_PORTS = {"ssh": ("ssh_port", 22), "scp": ("ssh_port", 22), "telnet": ("telnet_port", 23)}
GLOBAL_FALLBACKS = {
    "input": ("input.default", ("input", "default")),
    "output": ("output.default", ("output", "default")),
    "timeout": ("timeout", ("timeout",)),
}


def _scope(node: Node, config: dict[str, Any], groups: dict[str, Any]):
    group = groups.get(node.group_name) if node.group_name else None
    group = group if isinstance(group, dict) else None
    group_models = group.get("models") if group and isinstance(group.get("models"), dict) else {}
    group_model = group_models.get(node.model) if isinstance(group_models, dict) else None
    group_model = group_model if isinstance(group_model, dict) else None
    models = config.get("models") if isinstance(config.get("models"), dict) else {}
    model = models.get(node.model) if isinstance(models, dict) else None
    model = model if isinstance(model, dict) else None
    return group, group_model, model


def _pick(scopes: list[tuple[str, str | None, Any]], key: str) -> dict[str, Any]:
    for source, detail, scope in scopes:
        if not isinstance(scope, dict):
            continue
        value = scope.get(key)
        if value is not None and value != "":
            return {"value": value, "source": source, "source_detail": detail}
    return {"value": None, "source": "missing", "source_detail": None}


def _global(config: dict[str, Any], *path: str) -> Any:
    value: Any = config
    for key in path:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def _with_global(result: dict[str, Any], key: str, config: dict[str, Any]) -> dict[str, Any]:
    if result["value"] is not None:
        return result
    if key in GLOBAL_FALLBACKS:
        detail, path = GLOBAL_FALLBACKS[key]
        value = _global(config, *path)
    else:
        detail, value = key, config.get(key)
    if value is not None and value != "":
        return {"value": value, "source": "config", "source_detail": detail}
    return result


def _detail(node: Node) -> str:
    return f"{node.group_name}/{node.model}" if node.group_name else node.model


def _port(node: Node, input_value: dict[str, Any], vars_scopes: list[tuple[str, str | None, Any]]) -> dict[str, Any]:
    if node.port is not None:
        return {"value": str(node.port), "source": "node", "source_detail": None}
    protocols = [part.strip().lower() for part in str(input_value["value"] or "").split(",") if part.strip()]
    entries: list[tuple[str, int, str, str | None]] = []
    for protocol in protocols:
        protocol_config = PROTOCOL_PORTS.get(protocol)
        if protocol_config is None:
            continue
        var_name, default_port = protocol_config
        found = _pick(vars_scopes, var_name)
        if found["value"] is not None:
            try:
                port = int(found["value"])
            except (TypeError, ValueError):
                port = default_port
            entries.append((protocol, port, str(found["source"]), found["source_detail"]))
        else:
            entries.append((protocol, default_port, "default", None))
    if not entries:
        return {"value": None, "source": "missing", "source_detail": None}
    sources = {entry[2] for entry in entries}
    ports = {entry[1] for entry in entries}
    if len(ports) == 1:
        port, source, detail = entries[0][1], entries[0][2], entries[0][3]
        return {"value": str(port), "source": source if len(sources) == 1 else "mixed", "source_detail": detail}
    value = ", ".join(f"{port} ({protocol.upper()})" for protocol, port, _source, _detail in entries)
    return {"value": value, "source": entries[0][2] if len(sources) == 1 else "mixed", "source_detail": None}


def effective_settings(
    node: Node,
    *,
    config: dict[str, Any],
    groups: dict[str, Any],
    node_password: str | None,
    node_enable: str | None,
) -> dict[str, Any]:
    """Resolve the values Oxidized will actually use for a node.

    The precedence matches Oxidized's ``Node#resolve_key``:
    node -> group model -> group -> model -> global configuration.
    """
    group, group_model, model = _scope(node, config, groups)
    detail = _detail(node)
    node_values = {
        "input": node.input,
        "output": node.output,
        "username": node.username,
        "password": node_password,
        "timeout": node.timeout_seconds,
        "prompt": node.prompt,
    }
    scopes: list[tuple[str, str | None, Any]] = [
        ("node", None, node_values),
        ("group_model", detail if group_model else None, group_model),
        ("group", node.group_name, group),
        ("model", node.model, model),
    ]
    vars_scopes: list[tuple[str, str | None, Any]] = [
        ("node", None, node_vars(node)),
        ("group_model", detail if group_model else None, group_model.get("vars") if group_model else None),
        ("group", node.group_name, group.get("vars") if group else None),
        ("model", node.model, model.get("vars") if model else None),
        ("config", None, config.get("vars")),
    ]
    if node_enable:
        node_vars_value = vars_scopes[0][2]
        if not isinstance(node_vars_value, dict):
            node_vars_value = {}
        vars_scopes[0] = ("node", None, {**node_vars_value, "enable": node_enable})

    input_value = _with_global(_pick(scopes, "input"), "input", config)
    output_value = _with_global(_pick(scopes, "output"), "output", config)
    timeout_value = _with_global(_pick(scopes, "timeout"), "timeout", config)
    username_value = _with_global(_pick(scopes, "username"), "username", config)
    password_value = _with_global(_pick(scopes, "password"), "password", config)
    enable_value = _pick(vars_scopes, "enable")
    prompt_value = {
        "value": node.prompt,
        "source": "node" if node.prompt else "model_or_config",
        "source_detail": None,
    }

    return {
        "input": input_value,
        "port": _port(node, input_value, vars_scopes),
        "username": username_value,
        "password": {
            "set": bool(password_value["value"]),
            "source": password_value["source"],
            "source_detail": password_value["source_detail"],
        },
        "enable": {
            "set": bool(enable_value["value"]),
            "source": enable_value["source"],
            "source_detail": enable_value["source_detail"],
        },
        "output": output_value,
        "timeout_seconds": timeout_value,
        "prompt": prompt_value,
    }


def effective_node_settings(db: Session, node: Node) -> dict[str, Any]:
    config = applied_config(db)
    groups = config.get("groups") if isinstance(config.get("groups"), dict) else {}
    try:
        node_password = decrypt_optional(node.password_ciphertext)
    except Exception:  # noqa: BLE001 - a damaged secret must not hide the rest
        node_password = None
    try:
        node_enable = decrypt_optional(node.enable_ciphertext)
    except Exception:  # noqa: BLE001 - a damaged secret must not hide the rest
        node_enable = None
    return effective_settings(
        node,
        config=config,
        groups=groups,
        node_password=node_password,
        node_enable=node_enable,
    )
