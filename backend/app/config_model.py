from __future__ import annotations

import copy
import hashlib
import json
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .errors import AppError
from .schemas import GROUP_NAME_RE, MODEL_RE
from .settings import settings
from .yaml_codec import REGEXP_MARKER, dump_yaml, parse_config_yaml

MANAGED_SOURCE_KEYS = ("url", "headers", "map", "vars_map")
MANAGED_EXTENSION_KEYS = ("load", "listen", "port", "url_prefix")
REGEXP_RE = re.compile(r"^/(.*)/([imxouesn]*)$", re.DOTALL)
TOP_LEVEL_SECRET_KEYS = ("password",)


class MapEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    match: str = Field(min_length=1, max_length=128)
    target: str = Field(min_length=1, max_length=128)
    is_regex: bool = False

    @field_validator("match")
    @classmethod
    def _match(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("empty match")
        return value

    @field_validator("target")
    @classmethod
    def _target(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("empty target")
        return value

    @model_validator(mode="after")
    def _regexp(self) -> MapEntry:
        if self.is_regex and not REGEXP_RE.match(self.match):
            raise ValueError("regexp keys must use /pattern/flags")
        return self


class ScopeConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    username: str | None = Field(default=None, max_length=128)
    password: str | None = Field(default=None, max_length=512)
    vars: dict[str, Any] = Field(default_factory=dict)


class GroupConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    username: str | None = Field(default=None, max_length=128)
    password: str | None = Field(default=None, max_length=512)
    vars: dict[str, Any] = Field(default_factory=dict)
    models: dict[str, ScopeConfig] = Field(default_factory=dict)

    @field_validator("models")
    @classmethod
    def _models(cls, value: dict[str, ScopeConfig]) -> dict[str, ScopeConfig]:
        for name in value:
            if not MODEL_RE.fullmatch(name):
                raise ValueError(f"invalid model name: {name}")
        return value


class HookConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: str = Field(min_length=1, max_length=64)
    events: list[str] = Field(default_factory=list)
    timeout: int | None = Field(default=None, ge=1, le=86400)
    async_: bool | None = Field(default=None, alias="async", serialization_alias="async")

    @field_validator("events")
    @classmethod
    def _events(cls, value: list[str]) -> list[str]:
        for event in value:
            if not re.fullmatch(r"[a-z_]{1,64}", event):
                raise ValueError("invalid event")
        return value


class ConfigModel(BaseModel):
    model_config = ConfigDict(extra="allow")

    username: str | None = Field(default=None, max_length=128)
    password: str | None = Field(default=None, max_length=512)
    model: str | None = Field(default=None, max_length=128)
    interval: int | None = Field(default=None, ge=0, le=604800)
    threads: int | None = Field(default=None, ge=1, le=256)
    use_max_threads: bool | None = None
    timeout: int | None = Field(default=None, ge=1, le=3600)
    timelimit: int | None = Field(default=None, ge=1, le=86400)
    retries: int | None = Field(default=None, ge=0, le=20)
    prompt: str | None = Field(default=None, max_length=512)
    next_adds_job: bool | None = None
    resolve_dns: bool | None = None
    debug: bool | None = None
    run_once: bool | None = None
    pid: str | None = Field(default=None, max_length=512)
    use_syslog: bool | None = None
    log: str | None = Field(default=None, max_length=512)

    vars: dict[str, Any] = Field(default_factory=dict)
    groups: dict[str, GroupConfig] = Field(default_factory=dict)
    models: dict[str, ScopeConfig] = Field(default_factory=dict)
    group_map: list[MapEntry] = Field(default_factory=list)
    model_map: list[MapEntry] = Field(default_factory=list)
    input: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] = Field(default_factory=dict)
    source: dict[str, Any] = Field(default_factory=dict)
    hooks: dict[str, HookConfig] = Field(default_factory=dict)
    extensions: dict[str, Any] = Field(default_factory=dict)
    logger: dict[str, Any] = Field(default_factory=dict)
    crash: dict[str, Any] = Field(default_factory=dict)
    stats: dict[str, Any] = Field(default_factory=dict)

    @field_validator("prompt")
    @classmethod
    def _prompt(cls, value: str | None) -> str | None:
        if value is not None and ("\n" in value or "\r" in value):
            raise ValueError("prompt cannot contain newlines")
        return value

    @field_validator("groups")
    @classmethod
    def _groups(cls, value: dict[str, GroupConfig]) -> dict[str, GroupConfig]:
        for name in value:
            if not GROUP_NAME_RE.fullmatch(name):
                raise ValueError(f"invalid group name: {name}")
        return value

    @field_validator("models")
    @classmethod
    def _models(cls, value: dict[str, ScopeConfig]) -> dict[str, ScopeConfig]:
        for name in value:
            if not MODEL_RE.fullmatch(name):
                raise ValueError(f"invalid model name: {name}")
        return value

    @field_validator("hooks")
    @classmethod
    def _hooks(cls, value: dict[str, HookConfig]) -> dict[str, HookConfig]:
        for name, hook in value.items():
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", name):
                raise ValueError(f"invalid hook name: {name}")
            if not hook.type:
                raise ValueError(f"hook {name} has no type")
        return value


DEFAULT_CONFIG: dict[str, Any] = {
    "interval": 3600,
    "threads": 30,
    "use_max_threads": False,
    "timeout": 20,
    "timelimit": 300,
    "retries": 3,
    "prompt": r"^([\w.@-]+[#>]\s?)$",
    "next_adds_job": True,
    "resolve_dns": True,
    "debug": False,
    "vars": {},
    "groups": {},
    "models": {},
    "group_map": [],
    "model_map": [
        {"match": "juniper", "target": "junos", "is_regex": False},
        {"match": "cisco", "target": "ios", "is_regex": False},
    ],
    "input": {
        "default": "ssh, telnet",
        "debug": False,
        "ssh": {"secure": False},
        "ftp": {"passive": True},
    },
    "output": {
        "default": "git",
        "git": {
            "user": "Oxidized",
            "email": "oxidized@example.com",
            "repo": "/var/lib/oxidized/devices.git",
            "single_repo": True,
        },
    },
    "source": {"http": {"read_timeout": 30}},
    "extensions": {
        "oxidized-web": {
            "hide_node_vars": ["enable", "password"],
            "vhosts": [],
        }
    },
    "crash": {"directory": "~/.config/oxidized/crashes", "hostnames": False},
    "stats": {"history_size": 10},
    "hooks": {},
}


def validate_config(raw: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise AppError("config.validation_failed", params={"reason": "not_mapping"})
    if "rest" in raw:
        raise AppError("config.managed_key_modified", params={"key": "rest"})
    if len(json.dumps(raw, ensure_ascii=False).encode("utf-8")) > settings.max_config_bytes:
        raise AppError("config.content_too_large")

    source = raw.get("source")
    if source is not None:
        if not isinstance(source, dict):
            raise AppError(
                "config.validation_failed", fields=[{"path": "source", "code": "validation.invalid_type", "params": {}}]
            )
        if "default" in source:
            raise AppError("config.managed_key_modified", params={"key": "source.default"})
        http = source.get("http")
        if http is not None and not isinstance(http, dict):
            raise AppError(
                "config.validation_failed",
                fields=[{"path": "source.http", "code": "validation.invalid_type", "params": {}}],
            )
        for key in MANAGED_SOURCE_KEYS:
            if isinstance(http, dict) and key in http:
                raise AppError("config.managed_key_modified", params={"key": f"source.http.{key}"})
    extensions = raw.get("extensions")
    if extensions is not None:
        if not isinstance(extensions, dict):
            raise AppError(
                "config.validation_failed",
                fields=[{"path": "extensions", "code": "validation.invalid_type", "params": {}}],
            )
        web = extensions.get("oxidized-web")
        if isinstance(web, dict):
            for key in MANAGED_EXTENSION_KEYS:
                if key in web:
                    raise AppError("config.managed_key_modified", params={"key": f"extensions.oxidized-web.{key}"})
    try:
        model = ConfigModel.model_validate(raw)
    except Exception as exc:  # noqa: BLE001 - convert Pydantic errors into stable codes
        fields = _pydantic_fields(exc)
        raise AppError("config.validation_failed", fields=fields) from exc
    # extras and explicitly-set None values survive; defaults for omitted fields
    # are supplied by the catalog/renderer, not silently written to the file.
    normalized = model.model_dump(exclude_unset=True, mode="json", by_alias=True)
    _validate_semantics(normalized)
    return normalized


def _pydantic_fields(exc: Exception) -> list[dict[str, Any]]:
    fields: list[dict[str, Any]] = []
    errors = getattr(exc, "errors", lambda: [])()
    for item in errors:
        loc = ".".join(str(part) for part in item.get("loc", [])) or "config"
        fields.append(
            {
                "path": loc,
                "code": "validation.invalid_format",
                "params": {"reason": str(item.get("msg", "invalid"))[:200]},
            }
        )
    return fields or [{"path": "config", "code": "validation.failed", "params": {}}]


def _validate_semantics(config: dict[str, Any]) -> None:
    prompt = config.get("prompt")
    if prompt is not None and not isinstance(prompt, str):
        raise AppError("config.validation_failed", params={"reason": "prompt_not_string"})
    timelimit = config.get("timelimit")
    timeout = config.get("timeout")
    if isinstance(timelimit, int) and isinstance(timeout, int) and timelimit < timeout:
        # Not fatal in Oxidized, but a configuration that cannot finish a single
        # network operation is almost certainly a mistake.
        raise AppError(
            "config.validation_failed",
            fields=[{"path": "timelimit", "code": "validation.min", "params": {"min": timeout}}],
        )
    output = config.get("output")
    if isinstance(output, dict) and "default" in output and not isinstance(output["default"], str):
        raise AppError("config.validation_failed", params={"reason": "output_default"})
    input_cfg = config.get("input")
    if isinstance(input_cfg, dict) and "default" in input_cfg and not isinstance(input_cfg["default"], str):
        raise AppError("config.validation_failed", params={"reason": "input_default"})
    source = config.get("source")
    if isinstance(source, dict):
        http = source.get("http")
        if isinstance(http, dict) and "read_timeout" in http:
            read_timeout = http["read_timeout"]
            if not isinstance(read_timeout, int) or not 5 <= read_timeout <= 300:
                raise AppError(
                    "config.validation_failed",
                    fields=[{"path": "source.http.read_timeout", "code": "validation.min", "params": {"min": 5}}],
                )
    extensions = config.get("extensions")
    if isinstance(extensions, dict):
        web = extensions.get("oxidized-web")
        if isinstance(web, dict):
            vhosts = web.get("vhosts")
            if vhosts is not None:
                if not isinstance(vhosts, list) or not all(isinstance(item, str) for item in vhosts):
                    raise AppError("config.validation_failed", params={"reason": "vhosts_not_list"})
                if vhosts and "oxidized" not in vhosts:
                    raise AppError(
                        "config.validation_failed",
                        fields=[
                            {
                                "path": "extensions.oxidized-web.vhosts",
                                "code": "validation.invalid_choice",
                                "params": {"required": "oxidized"},
                            }
                        ],
                    )
            hide = web.get("hide_node_vars")
            if hide is not None and (not isinstance(hide, list) or not all(isinstance(item, str) for item in hide)):
                raise AppError("config.validation_failed", params={"reason": "hide_node_vars_not_list"})
    for section in ("group_map", "model_map"):
        entries = config.get(section)
        if entries is None:
            continue
        if not isinstance(entries, list):
            raise AppError("config.validation_failed", params={"reason": f"{section}_not_list"})
        pattern = GROUP_NAME_RE if section == "group_map" else MODEL_RE
        for entry in entries:
            if not isinstance(entry, dict):
                raise AppError("config.validation_failed", params={"reason": f"{section}_entry"})
            target = entry.get("target")
            if not isinstance(target, str) or not pattern.fullmatch(target):
                raise AppError(
                    "config.validation_failed",
                    fields=[{"path": f"{section}.target", "code": "validation.invalid_format", "params": {}}],
                )
    for name, group in (config.get("groups") or {}).items():
        if not isinstance(group, dict):
            raise AppError("config.validation_failed", params={"reason": "group_not_mapping", "group": name})
        _validate_group_vars(name, group.get("vars") or {})
    for name, scope in (config.get("models") or {}).items():
        if not isinstance(scope, dict):
            raise AppError("config.validation_failed", params={"reason": "model_not_mapping", "model": name})
        _validate_group_vars(name, scope.get("vars") or {})


def _validate_group_vars(name: str, value: Any) -> None:
    if not isinstance(value, dict):
        raise AppError("config.validation_failed", params={"reason": "vars_not_mapping", "scope": name})


def normalize_config(raw: dict[str, Any]) -> dict[str, Any]:
    return validate_config(raw)


def config_json(config: dict[str, Any]) -> str:
    return json.dumps(config, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def config_hash(config: dict[str, Any]) -> str:
    return hashlib.sha256(config_json(config).encode("utf-8")).hexdigest()


def render_effective_config(config: dict[str, Any], *, preview: bool = False) -> str:
    effective = copy.deepcopy(config)
    source = effective.setdefault("source", {})
    if not isinstance(source, dict):
        raise AppError("config.validation_failed", params={"reason": "source"})
    source["default"] = "http"
    http = source.setdefault("http", {})
    if not isinstance(http, dict):
        raise AppError("config.validation_failed", params={"reason": "source_http"})
    http["url"] = settings.ui_internal_url.rstrip("/") + "/api/internal/source/nodes"
    token = "<managed-source-token>" if preview else settings.oxidized_source_token
    http["headers"] = {"X-Oxidized-Source-Token": token}
    http["map"] = {
        "name": "name",
        "ip": "ip",
        "model": "model",
        "group": "group",
        "input": "input",
        "username": "username",
        "password": "password",
        "vars": "vars",
        "output": "output",
        "prompt": "prompt",
        "timeout": "timeout",
    }
    http["vars_map"] = {}

    extensions = effective.setdefault("extensions", {})
    if not isinstance(extensions, dict):
        raise AppError("config.validation_failed", params={"reason": "extensions"})
    web = extensions.setdefault("oxidized-web", {})
    if not isinstance(web, dict):
        raise AppError("config.validation_failed", params={"reason": "extensions_web"})
    web["load"] = True
    web["listen"] = "0.0.0.0"
    web["port"] = 8888
    web.pop("url_prefix", None)

    return dump_yaml(effective)


def editable_yaml(config: dict[str, Any]) -> str:
    return dump_yaml(copy.deepcopy(config))


def load_editable_yaml(text: str) -> dict[str, Any]:
    config = parse_config_yaml(text)
    prompt = config.get("prompt")
    if isinstance(prompt, dict) and set(prompt.keys()) == {REGEXP_MARKER}:
        config["prompt"] = prompt[REGEXP_MARKER]
    return validate_config(config)


def mask_source_token(yaml_text: str) -> str:
    token = settings.oxidized_source_token
    return yaml_text.replace(token, "<managed-source-token>")


def default_config() -> dict[str, Any]:
    return copy.deepcopy(DEFAULT_CONFIG)


def config_groups(config: dict[str, Any]) -> dict[str, Any]:
    groups = config.get("groups") or {}
    return groups if isinstance(groups, dict) else {}


def node_group_names(config: dict[str, Any]) -> set[str]:
    return set(config_groups(config).keys())


def validate_nodes_use_known_groups(config: dict[str, Any], groups_in_use: set[str]) -> None:
    known = node_group_names(config)
    missing = sorted(group for group in groups_in_use if group not in known)
    if missing:
        raise AppError("config.group_in_use", params={"groups": missing})


def group_secret_state(group: dict[str, Any]) -> tuple[bool, bool]:
    vars_ = group.get("vars") or {}
    return bool(group.get("password")), bool(isinstance(vars_, dict) and vars_.get("enable"))


def redact_group_for_api(name: str, group: dict[str, Any]) -> dict[str, Any]:
    vars_ = group.get("vars") or {}
    if not isinstance(vars_, dict):
        vars_ = {}
    visible_vars = {key: value for key, value in vars_.items() if key != "enable"}
    models = group.get("models") or {}
    model_result: dict[str, Any] = {}
    if isinstance(models, dict):
        for model_name, scope in models.items():
            if not isinstance(scope, dict):
                continue
            scope_vars = scope.get("vars") or {}
            if not isinstance(scope_vars, dict):
                scope_vars = {}
            model_result[model_name] = {
                "username": scope.get("username"),
                "has_password": bool(scope.get("password")),
                "has_enable": bool(scope_vars.get("enable")),
                "vars": {key: value for key, value in scope_vars.items() if key != "enable"},
            }
    return {
        "name": name,
        "username": group.get("username"),
        "has_password": bool(group.get("password")),
        "has_enable": bool(vars_.get("enable")),
        "vars": visible_vars,
        "models": model_result,
    }


def apply_group_patch(existing: dict[str, Any], patch: dict[str, Any], *, is_create: bool = False) -> dict[str, Any]:
    group = copy.deepcopy(existing) if not is_create else {}
    for field in ("username",):
        if field in patch:
            group[field] = patch[field]
    if patch.get("password") is not None:
        group["password"] = patch["password"]
    if patch.get("clear_password"):
        group.pop("password", None)
    vars_ = group.setdefault("vars", {})
    if not isinstance(vars_, dict):
        vars_ = {}
        group["vars"] = vars_
    if "vars" in patch:
        previous_enable = vars_.get("enable")
        vars_ = {key: value for key, value in (patch.get("vars") or {}).items() if key != "enable"}
        if previous_enable is not None and "enable" not in patch and not patch.get("clear_enable"):
            vars_["enable"] = previous_enable
        group["vars"] = vars_
    if "enable" in patch and patch["enable"] is not None:
        vars_["enable"] = patch["enable"]
    if patch.get("clear_enable"):
        vars_.pop("enable", None)
    if "models" in patch:
        existing_models = group.get("models") or {}
        if not isinstance(existing_models, dict):
            existing_models = {}
        for model_name, model_patch in patch["models"].items():
            if not isinstance(model_patch, dict):
                continue
            if model_patch.get("remove"):
                existing_models.pop(model_name, None)
                continue
            scope = copy.deepcopy(existing_models.get(model_name) or {})
            if "username" in model_patch:
                scope["username"] = model_patch["username"]
            if "password" in model_patch and model_patch["password"] is not None:
                scope["password"] = model_patch["password"]
            if model_patch.get("clear_password"):
                scope.pop("password", None)
            scope_vars = scope.setdefault("vars", {})
            if not isinstance(scope_vars, dict):
                scope_vars = {}
                scope["vars"] = scope_vars
            if "vars" in model_patch:
                previous_enable = scope_vars.get("enable")
                scope_vars = {key: value for key, value in (model_patch.get("vars") or {}).items() if key != "enable"}
                if previous_enable is not None and "enable" not in model_patch and not model_patch.get("clear_enable"):
                    scope_vars["enable"] = previous_enable
                scope["vars"] = scope_vars
            if "enable" in model_patch and model_patch["enable"] is not None:
                scope_vars["enable"] = model_patch["enable"]
            if model_patch.get("clear_enable"):
                scope_vars.pop("enable", None)
            existing_models[model_name] = scope
        group["models"] = existing_models
    return group
