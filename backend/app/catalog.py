from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from .config_model import DEFAULT_CONFIG

DATA_DIR = Path(__file__).with_name("data")


def _slug(path: str) -> str:
    return path.replace(".", "_").replace("[]", "_item")


_UNSET = object()


def field(
    path: str,
    field_type: str,
    *,
    default: Any = _UNSET,
    section: str = "general",
    level: str = "basic",
    sensitive: bool = False,
    managed: bool = False,
    minimum: int | float | None = None,
    maximum: int | float | None = None,
    options: list[Any] | None = None,
    placeholder: str | None = None,
    deprecated: bool = False,
    help_code: str | None = None,
) -> dict[str, Any]:
    slug = _slug(path)
    result: dict[str, Any] = {
        "path": path,
        "type": field_type,
        "label_code": f"oxidized.fields.{slug}.label",
        "help_code": help_code or f"oxidized.fields.{slug}.help",
        "section": section,
        "level": level,
        "sensitive": sensitive,
        "managed": managed,
        "deprecated": deprecated,
    }
    if default is not _UNSET:
        result["default"] = default
    if minimum is not None:
        result["min"] = minimum
    if maximum is not None:
        result["max"] = maximum
    if options is not None:
        result["options"] = options
    if placeholder is not None:
        result["placeholder"] = placeholder
    return result


def _fields() -> list[dict[str, Any]]:
    fields = [
        field("username", "string", default=None, placeholder="oxidized"),
        field("password", "secret", sensitive=True),
        field("model", "select", default="junos", options="__models__"),
        field("interval", "integer", default=3600, minimum=0, maximum=604800),
        field("threads", "integer", default=30, minimum=1, maximum=256),
        field("use_max_threads", "boolean", default=False, level="advanced"),
        field("timeout", "integer", default=20, minimum=1, maximum=3600),
        field("timelimit", "integer", default=300, minimum=1, maximum=86400),
        field("retries", "integer", default=3, minimum=0, maximum=20),
        field("prompt", "regex", default=r"^([\w.@-]+[#>]\s?)$", level="advanced"),
        field("next_adds_job", "boolean", default=False),
        field("resolve_dns", "boolean", default=True, level="advanced"),
        field("debug", "boolean", default=False),
        field("run_once", "boolean", default=False, level="advanced", deprecated=False),
        field("pid", "string", default="~/.config/oxidized/pid", level="advanced"),
        field("use_syslog", "boolean", default=False, level="advanced", deprecated=True),
        field("log", "string", default=None, level="advanced", deprecated=True),
        field(
            "logger.level",
            "select",
            default=":info",
            options=[":trace", ":debug", ":info", ":warn", ":error", ":fatal"],
        ),
        field("logger.appenders", "json", default=[], level="advanced"),
        field("crash.directory", "string", default="~/.config/oxidized/crashes", level="advanced"),
        field("crash.hostnames", "boolean", default=False, level="advanced"),
        field("stats.history_size", "integer", default=10, minimum=1, maximum=100, level="advanced"),
        field("vars", "keyvalue", default={}, section="general"),
        field("group_map", "map_list", default=[], section="general"),
        field("model_map", "map_list", default=[], section="general"),
        field(
            "input.default",
            "multiselect",
            default="ssh, telnet",
            section="input",
            options=["ssh", "telnet", "scp", "ftp", "http", "tftp", "exec"],
        ),
        field("input.debug", "multiselect", default=False, section="input", options=["text", "yaml", "library"]),
        field("input.ssh.secure", "boolean", default=False, section="input"),
        field("input.ftp.passive", "boolean", default=True, section="input"),
        field("input.http.scheme", "select", default="http", section="input", options=["http", "https"]),
        field("input.http.ssl_verify", "boolean", default=False, section="input"),
        field("input.http.timeout", "integer", default=30, section="input", minimum=1, maximum=3600),
        field("input.utf8_encoded", "boolean", default=True, section="input", level="advanced"),
        field(
            "output.default", "select", default="file", section="output", options=["git", "file", "gitcrypt", "http"]
        ),
        field("output.clean_obsolete_nodes", "boolean", default=False, section="output", level="advanced"),
        field("output.file.directory", "string", default="/var/lib/oxidized/configs", section="output"),
        field("output.git.user", "string", default="Oxidized", section="output"),
        field("output.git.email", "string", default="oxidized@example.com", section="output"),
        field("output.git.repo", "string", default="/var/lib/oxidized/devices.git", section="output"),
        field("output.git.single_repo", "boolean", default=True, section="output", level="advanced"),
        field("output.git.type_as_directory", "boolean", default=False, section="output", level="advanced"),
        field("output.gitcrypt.user", "string", default="Oxidized", section="output"),
        field("output.gitcrypt.email", "string", default="oxidized@example.com", section="output"),
        field("output.gitcrypt.repo", "string", default="/var/lib/oxidized/devices.git", section="output"),
        field("output.gitcrypt.users", "list", default=[], section="output"),
        field("output.gitcrypt.single_repo", "boolean", default=True, section="output", level="advanced"),
        field("output.http.url", "string", section="output"),
        field("output.http.user", "string", section="output"),
        field("output.http.password", "secret", section="output", sensitive=True),
        field("output.http.ssl_verify", "boolean", default=False, section="output"),
        field("output.http.headers", "keyvalue", default={}, section="output"),
        field("source.http.read_timeout", "integer", default=30, section="source", minimum=5, maximum=300),
        field("source.default", "string", default="http", section="source", managed=True),
        field("source.http.url", "string", section="source", managed=True),
        field("source.http.headers", "keyvalue", section="source", managed=True, sensitive=True),
        field("source.http.map", "keyvalue", section="source", managed=True),
        field("source.http.vars_map", "keyvalue", default={}, section="source", managed=True),
        field("extensions.oxidized-web.load", "boolean", default=True, section="rest", managed=True),
        field("extensions.oxidized-web.listen", "string", default="0.0.0.0", section="rest", managed=True),
        field("extensions.oxidized-web.port", "integer", default=8888, section="rest", managed=True),
        field("extensions.oxidized-web.url_prefix", "string", default="", section="rest", managed=True),
        field("extensions.oxidized-web.vhosts", "list", default=[], section="rest"),
        field("extensions.oxidized-web.hide_node_vars", "list", default=["enable", "password"], section="rest"),
    ]
    return fields


@lru_cache(maxsize=1)
def models() -> list[str]:
    return json.loads((DATA_DIR / "oxidized_models.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def model_vendors() -> dict[str, str]:
    vendors = json.loads((DATA_DIR / "oxidized_model_vendors.json").read_text(encoding="utf-8"))
    return {name: vendors.get(name, "Otro") for name in models()}


def _vars() -> list[dict[str, Any]]:
    entries = [
        ("enable", "secret", "Enable/privileged password"),
        ("remove_secret", "boolean", "Remove secrets from configs"),
        ("metadata", "boolean", "Add metadata to outputs"),
        ("metadata_top", "string", "Metadata at the top"),
        ("metadata_bottom", "string", "Metadata at the bottom"),
        ("output_store_mode", "select", "When to store output"),
        ("ssh_no_exec", "boolean", "Disable SSH exec channel"),
        ("ssh_no_keepalive", "boolean", "Disable SSH keepalive"),
        ("ssh_keys", "string", "Private SSH key path"),
        ("auth_methods", "list", "SSH authentication methods"),
        ("ssh_proxy", "string", "SSH proxy host"),
        ("ssh_proxy_port", "integer", "SSH proxy port"),
        ("ssh_kex", "string", "SSH KEX algorithms"),
        ("ssh_host_key", "string", "SSH host key algorithms"),
        ("ssh_hmac", "string", "SSH HMAC algorithms"),
        ("ssh_encryption", "string", "SSH encryption algorithms"),
        ("ssh_pubkey_algorithms", "string", "SSH public key algorithms"),
        ("ssh_port", "integer", "SSH/SCP port"),
        ("telnet_port", "integer", "Telnet port"),
        ("comware_cmdline", "string", "Comware command line"),
        ("cumulus_use_nclu", "boolean", "Cumulus use NCLU"),
        ("cumulus_use_nvue", "boolean", "Cumulus use NVUE"),
        ("cumulus_routing_daemon", "string", "Cumulus routing daemon"),
        ("ftd_api_endpoint", "string", "FTD API endpoint"),
        ("ftd_api_port", "integer", "FTD API port"),
        ("ftd_polls", "integer", "FTD polls"),
        ("ftd_poll_wait", "integer", "FTD poll wait"),
        ("ftd_config_filename", "string", "FTD config filename"),
        ("fortios_autoupdate", "boolean", "FortiOS autoupdate"),
        ("fortigate_autoupdate", "boolean", "FortiGate autoupdate"),
        ("fullconfig", "boolean", "FortiGate full configuration"),
        ("ios_rbac", "boolean", "IOS RBAC"),
        ("lenovonos_remove_unstable_lines", "boolean", "Lenovo NOS remove unstable lines"),
        ("openwrt_binary_files", "list", "OpenWrt binary files"),
        ("openwrt_non_sensitive_files", "list", "OpenWrt non-sensitive files"),
        ("openwrt_partitions_to_backup", "list", "OpenWrt partitions to backup"),
        ("openwrt_backup_partitions", "boolean", "OpenWrt backup partitions"),
        ("realm", "string", "Ivanti realm"),
        ("admin", "boolean", "Enterprise SONiC admin mode"),
    ]
    result = []
    for name, type_, description in entries:
        result.append(
            {
                "name": name,
                "type": type_,
                "label_code": f"oxidized.vars.{name}.label",
                "help_code": f"oxidized.vars.{name}.help",
                "technical_description": description,
                "options": ["on_significant"] if name == "output_store_mode" else None,
            }
        )
    return result


def hook_catalog() -> dict[str, Any]:
    events = ["node_success", "node_fail", "post_store", "nodes_done"]
    hooks: dict[str, Any] = {}
    definitions = {
        "exec": [
            field("cmd", "string", section="hooks", help_code="oxidized.fields.hooks_exec_cmd.help"),
            field("timeout", "integer", default=60, minimum=1, maximum=86400, section="hooks"),
            field("async", "boolean", default=False, section="hooks"),
        ],
        "githubrepo": [
            field("remote_repo", "string", section="hooks"),
            field("username", "string", section="hooks"),
            field("password", "secret", section="hooks", sensitive=True),
            field("privatekey", "string", section="hooks"),
            field("publickey", "string", section="hooks"),
        ],
        "awssns": [
            field("region", "string", section="hooks"),
            field("topic_arn", "string", section="hooks"),
        ],
        "slackdiff": [
            field("token", "secret", section="hooks", sensitive=True),
            field("channel", "string", section="hooks"),
            field("diff", "boolean", default=True, section="hooks"),
            field("message", "string", section="hooks"),
            field("proxy", "string", section="hooks"),
        ],
        "ciscosparkdiff": [
            field("accesskey", "secret", section="hooks", sensitive=True),
            field("space", "string", section="hooks"),
            field("diff", "boolean", default=True, section="hooks"),
            field("message", "string", section="hooks"),
            field("proxy", "string", section="hooks"),
        ],
        "xmppdiff": [
            field("jid", "string", section="hooks"),
            field("password", "secret", section="hooks", sensitive=True),
            field("channel", "string", section="hooks"),
            field("nick", "string", section="hooks"),
        ],
    }
    labels = {
        "exec": "Exec command",
        "githubrepo": "GitHub repository",
        "awssns": "AWS SNS",
        "slackdiff": "Slack diff",
        "ciscosparkdiff": "Cisco Spark diff",
        "xmppdiff": "XMPP diff",
    }
    for name, defs in definitions.items():
        hooks[name] = {
            "name": name,
            "label_code": f"oxidized.hooks.{name}.label",
            "help_code": f"oxidized.hooks.{name}.help",
            "technical_description": labels[name],
            "events": events,
            "suggested_events": ["post_store"] if name.endswith("diff") else events,
            "fields": defs,
        }
    return hooks


@lru_cache(maxsize=1)
def catalog() -> dict[str, Any]:
    return {
        "fields": _fields(),
        "sections": [
            {"id": "general", "label_code": "oxidized.tabs.general"},
            {"id": "input", "label_code": "oxidized.tabs.input"},
            {"id": "output", "label_code": "oxidized.tabs.output"},
            {"id": "source", "label_code": "oxidized.tabs.source"},
            {"id": "hooks", "label_code": "oxidized.tabs.hooks"},
            {"id": "models", "label_code": "oxidized.tabs.models"},
            {"id": "rest", "label_code": "oxidized.tabs.rest"},
            {"id": "advanced", "label_code": "oxidized.tabs.advanced"},
        ],
        "models": models(),
        "model_vendors": model_vendors(),
        "inputs": ["ssh", "telnet", "scp", "ftp", "http", "tftp", "exec"],
        "outputs": ["git", "file", "gitcrypt", "http"],
        "hook_types": hook_catalog(),
        "vars": _vars(),
        "managed_keys": [
            "source.default",
            "source.http.url",
            "source.http.headers.X-Oxidized-Source-Token",
            "source.http.map",
            "source.http.vars_map",
            "extensions.oxidized-web.load",
            "extensions.oxidized-web.listen",
            "extensions.oxidized-web.port",
            "extensions.oxidized-web.url_prefix",
        ],
        "defaults": default_snapshot(),
    }


def default_snapshot() -> dict[str, Any]:
    # Avoid import-time copying cost; DEFAULT_CONFIG is not mutated.
    return DEFAULT_CONFIG
