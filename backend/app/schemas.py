from __future__ import annotations

import ipaddress
import re
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ROLE = Literal["admin", "operator", "viewer"]
THEME = Literal["light", "dark", "system"]
KNOWN_INPUTS = ("ssh", "telnet", "scp", "ftp", "http", "tftp", "exec")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalize_full_name(value: str | None) -> str | None:
    if value is None:
        return None
    text = " ".join(value.split())
    return text or None


def normalize_email(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip().casefold()
    if not text:
        return None
    if not EMAIL_RE.fullmatch(text):
        raise ValueError("invalid email address")
    return text
RESERVED_VARS = {"enable", "password", "username", "name", "ip", "model", "group"}
NODE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,252}$")
MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
GROUP_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
VAR_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]{0,127}$")
HOST_LABEL_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LoginRequest(StrictModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=512)


class SetupRequest(StrictModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=512)
    language: str = Field(default="es", max_length=16)
    theme: THEME = "system"


class SessionUser(BaseModel):
    id: int
    username: str
    role: str
    language: str
    theme: str


class ProfileUpdate(StrictModel):
    language: str | None = Field(default=None, max_length=16)
    theme: THEME | None = None
    full_name: str | None = Field(default=None, max_length=128)
    email: str | None = Field(default=None, max_length=254)

    @field_validator("full_name")
    @classmethod
    def _full_name(cls, value: str | None) -> str | None:
        return normalize_full_name(value)

    @field_validator("email")
    @classmethod
    def _email(cls, value: str | None) -> str | None:
        return normalize_email(value)


class PasswordChangeRequest(StrictModel):
    current_password: str = Field(min_length=1, max_length=512)
    new_password: str = Field(min_length=1, max_length=512)


class ExportRequest(StrictModel):
    passphrase: str = Field(min_length=12, max_length=256)


class ApiTokenCreate(StrictModel):
    name: str = Field(min_length=1, max_length=100)
    role: Literal["admin", "operator", "viewer"] = "viewer"
    days: int = Field(default=90, ge=1, le=365)


class MfaCodeRequest(StrictModel):
    code: str = Field(min_length=4, max_length=32)


class MfaDisableRequest(StrictModel):
    password: str = Field(min_length=1, max_length=512)
    code: str = Field(min_length=4, max_length=32)


class MfaLoginRequest(StrictModel):
    challenge_token: str = Field(min_length=16, max_length=256)
    code: str = Field(min_length=4, max_length=32)


class UserCreate(StrictModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=512)
    role: ROLE = "viewer"
    language: str = Field(default="es", max_length=16)
    full_name: str | None = Field(default=None, max_length=128)
    email: str | None = Field(default=None, max_length=254)
    scope_groups: list[str] | None = Field(default=None, max_length=200)

    @field_validator("full_name")
    @classmethod
    def _full_name(cls, value: str | None) -> str | None:
        return normalize_full_name(value)

    @field_validator("email")
    @classmethod
    def _email(cls, value: str | None) -> str | None:
        return normalize_email(value)


class UserUpdate(StrictModel):
    role: ROLE | None = None
    is_active: bool | None = None
    language: str | None = Field(default=None, max_length=16)
    full_name: str | None = Field(default=None, max_length=128)
    email: str | None = Field(default=None, max_length=254)
    scope_groups: list[str] | None = Field(default=None, max_length=200)

    @field_validator("full_name")
    @classmethod
    def _full_name(cls, value: str | None) -> str | None:
        return normalize_full_name(value)

    @field_validator("email")
    @classmethod
    def _email(cls, value: str | None) -> str | None:
        return normalize_email(value)


class UserPasswordReset(StrictModel):
    new_password: str = Field(min_length=1, max_length=512)


def validate_node_name(value: str) -> str:
    value = value.strip()
    if not NODE_NAME_RE.fullmatch(value):
        from .errors import AppError

        raise AppError("node.invalid_name")
    if value.casefold().endswith(".json"):
        from .errors import AppError

        raise AppError("node.invalid_name", params={"reason": "json_suffix"})
    return value


def validate_group_name(value: str) -> str:
    value = value.strip()
    if not GROUP_NAME_RE.fullmatch(value):
        from .errors import AppError

        raise AppError("group.invalid_name")
    return value


def validate_model_name(value: str) -> str:
    value = value.strip()
    if not MODEL_RE.fullmatch(value):
        from .errors import AppError

        raise AppError("node.invalid_model")
    return value


def validate_address(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    if len(value) > 253 or re.search(r"[\s/\\]", value):
        from .errors import AppError

        raise AppError("node.invalid_address")
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        pass
    labels = value.rstrip(".").split(".")
    if all(HOST_LABEL_RE.fullmatch(label) for label in labels):
        if re.fullmatch(r"[0-9.]+", value):
            # Looks like a malformed IPv4; do not silently accept it as a hostname.
            from .errors import AppError

            raise AppError("node.invalid_address")
        return value
    from .errors import AppError

    raise AppError("node.invalid_address")


def normalize_input(value: str | None) -> str | None:
    if value is None:
        return None
    parts = [part.strip() for part in value.split(",") if part.strip()]
    if not parts:
        return None
    if len(set(parts)) != len(parts):
        from .errors import AppError

        raise AppError("node.invalid_input", params={"reason": "duplicate"})
    for part in parts:
        if part not in KNOWN_INPUTS:
            from .errors import AppError

            raise AppError("node.invalid_input", params={"input": part})
    return ", ".join(parts)


def validate_vars(value: dict[str, Any] | None) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        from .errors import AppError

        raise AppError("node.invalid_vars")
    if len(value) > 200:
        from .errors import AppError

        raise AppError("node.invalid_vars", params={"reason": "too_many"})
    clean: dict[str, Any] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not VAR_NAME_RE.fullmatch(key):
            from .errors import AppError

            raise AppError("node.invalid_vars", params={"key": str(key)[:128]})
        if key.casefold() in RESERVED_VARS:
            from .errors import AppError

            raise AppError("node.reserved_var", params={"name": key})
        clean[key] = item
    import json

    try:
        serialized = json.dumps(clean, ensure_ascii=False)
    except (TypeError, ValueError) as exc:
        from .errors import AppError

        raise AppError("node.invalid_vars", params={"reason": "not_json"}) from exc
    if len(serialized.encode("utf-8")) > 262_144:
        from .errors import AppError

        raise AppError("node.invalid_vars", params={"reason": "too_large"})
    return clean


class NodeCreate(StrictModel):
    name: str
    address: str | None = None
    model: str
    group_name: str | None = None
    input: str | None = None
    port: int | None = None
    username: str | None = Field(default=None, max_length=128)
    password: str | None = Field(default=None, max_length=512)
    enable: str | None = Field(default=None, max_length=512)
    vars: dict[str, Any] | None = None
    output: str | None = Field(default=None, max_length=128)
    prompt: str | None = Field(default=None, max_length=512)
    timeout_seconds: int | None = None
    tags: dict[str, str] | None = None

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        return validate_node_name(value)

    @field_validator("model")
    @classmethod
    def _model(cls, value: str) -> str:
        return validate_model_name(value)

    @field_validator("address")
    @classmethod
    def _address(cls, value: str | None) -> str | None:
        return validate_address(value)

    @field_validator("input")
    @classmethod
    def _input(cls, value: str | None) -> str | None:
        return normalize_input(value)

    @field_validator("vars")
    @classmethod
    def _vars(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        return validate_vars(value)

    @field_validator("group_name")
    @classmethod
    def _group(cls, value: str | None) -> str | None:
        return validate_group_name(value) if value else None

    @field_validator("port")
    @classmethod
    def _port(cls, value: int | None) -> int | None:
        if value is not None and not 1 <= value <= 65535:
            from .errors import AppError

            raise AppError("node.invalid_port", params={"port": value})
        return value

    @field_validator("timeout_seconds")
    @classmethod
    def _timeout(cls, value: int | None) -> int | None:
        if value is not None and not 1 <= value <= 3600:
            from .errors import AppError

            raise AppError("validation.max", params={"field": "timeout_seconds", "max": 3600})
        return value


class NodeUpdate(StrictModel):
    name: str | None = None
    address: str | None = None
    model: str | None = None
    group_name: str | None = None
    input: str | None = None
    port: int | None = None
    username: str | None = Field(default=None, max_length=128)
    password: str | None = Field(default=None, max_length=512)
    enable: str | None = Field(default=None, max_length=512)
    clear_password: bool = False
    clear_enable: bool = False
    vars: dict[str, Any] | None = None
    output: str | None = Field(default=None, max_length=128)
    prompt: str | None = Field(default=None, max_length=512)
    timeout_seconds: int | None = None
    tags: dict[str, str] | None = None

    @field_validator("name")
    @classmethod
    def _name(cls, value: str | None) -> str | None:
        return validate_node_name(value) if value is not None else None

    @field_validator("model")
    @classmethod
    def _model(cls, value: str | None) -> str | None:
        return validate_model_name(value) if value is not None else None

    @field_validator("address")
    @classmethod
    def _address(cls, value: str | None) -> str | None:
        return validate_address(value)

    @field_validator("input")
    @classmethod
    def _input(cls, value: str | None) -> str | None:
        return normalize_input(value)

    @field_validator("vars")
    @classmethod
    def _vars(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        return validate_vars(value)

    @field_validator("group_name")
    @classmethod
    def _group(cls, value: str | None) -> str | None:
        return validate_group_name(value) if value else None

    @field_validator("port")
    @classmethod
    def _port(cls, value: int | None) -> int | None:
        if value is not None and not 1 <= value <= 65535:
            from .errors import AppError

            raise AppError("node.invalid_port", params={"port": value})
        return value

    @field_validator("timeout_seconds")
    @classmethod
    def _timeout(cls, value: int | None) -> int | None:
        if value is not None and not 1 <= value <= 3600:
            from .errors import AppError

            raise AppError("validation.max", params={"field": "timeout_seconds", "max": 3600})
        return value

    @model_validator(mode="after")
    def _secret_conflicts(self) -> NodeUpdate:
        if self.clear_password and self.password is not None:
            from .errors import AppError

            raise AppError("node.credentials_read_only", params={"reason": "password_both"})
        if self.clear_enable and self.enable is not None:
            from .errors import AppError

            raise AppError("node.credentials_read_only", params={"reason": "enable_both"})
        return self


class NodeIdsRequest(StrictModel):
    ids: list[int] = Field(min_length=1, max_length=1000)


class NodeTemplateCreate(StrictModel):
    name: str = Field(min_length=1, max_length=100)
    model: str = Field(min_length=1, max_length=128)
    group_name: str | None = Field(default=None, max_length=128)
    input: str | None = Field(default=None, max_length=128)
    port: int | None = Field(default=None, ge=1, le=65535)
    username: str | None = Field(default=None, max_length=128)
    output: str | None = Field(default=None, max_length=128)
    prompt: str | None = Field(default=None, max_length=512)
    timeout_seconds: int | None = Field(default=None, ge=1, le=3600)
    vars: dict[str, Any] | None = None


class NodeTemplateUpdate(StrictModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    model: str | None = Field(default=None, min_length=1, max_length=128)
    group_name: str | None = Field(default=None, max_length=128)
    input: str | None = Field(default=None, max_length=128)
    port: int | None = Field(default=None, ge=1, le=65535)
    username: str | None = Field(default=None, max_length=128)
    output: str | None = Field(default=None, max_length=128)
    prompt: str | None = Field(default=None, max_length=512)
    timeout_seconds: int | None = Field(default=None, ge=1, le=3600)
    vars: dict[str, Any] | None = None


class NodeTemplateApply(StrictModel):
    name: str = Field(min_length=1, max_length=253)
    address: str | None = Field(default=None, max_length=253)
    tags: dict[str, str] | None = None


class ReconciliationImport(StrictModel):
    names: list[str] = Field(min_length=1, max_length=200)


class NodeBulkRequest(StrictModel):
    action: Literal[
        "backup",
        "change_group",
        "delete",
        "update",
        "trust_host_key",
        "set_tags",
        "test_connection",
    ]
    ids: list[int] = Field(min_length=1, max_length=1000)
    group_name: str | None = None
    model: str | None = Field(default=None, max_length=64)
    input: str | None = Field(default=None, max_length=32)
    port: int | None = Field(default=None, ge=1, le=65535)
    vars: dict[str, Any] | None = None
    tags: dict[str, str] | None = None
    tags_mode: Literal["merge", "replace"] = "merge"

    @field_validator("group_name")
    @classmethod
    def _group(cls, value: str | None) -> str | None:
        return validate_group_name(value) if value else None


class GroupModelWrite(StrictModel):
    username: str | None = Field(default=None, max_length=128)
    password: str | None = Field(default=None, max_length=512)
    clear_password: bool = False
    enable: str | None = Field(default=None, max_length=512)
    clear_enable: bool = False
    vars: dict[str, Any] = Field(default_factory=dict)
    remove: bool = False


class GroupWrite(StrictModel):
    username: str | None = Field(default=None, max_length=128)
    password: str | None = Field(default=None, max_length=512)
    clear_password: bool = False
    enable: str | None = Field(default=None, max_length=512)
    clear_enable: bool = False
    vars: dict[str, Any] = Field(default_factory=dict)
    models: dict[str, GroupModelWrite] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _conflicts(self) -> GroupWrite:
        if self.clear_password and self.password is not None:
            from .errors import AppError

            raise AppError("group.password_change_failed", params={"reason": "password_both"})
        if self.clear_enable and self.enable is not None:
            from .errors import AppError

            raise AppError("group.password_change_failed", params={"reason": "enable_both"})
        return self


class GroupCreate(GroupWrite):
    name: str

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        return validate_group_name(value)


class ConfigDraftRequest(StrictModel):
    config: dict[str, Any] | None = None
    yaml: str | None = None
    expected_revision_id: int | None = None
    note: str | None = Field(default=None, max_length=500)
    origin: Literal["form", "yaml"] = "form"

    @model_validator(mode="after")
    def _one_content(self) -> ConfigDraftRequest:
        if (self.config is None) == (self.yaml is None):
            from .errors import AppError

            raise AppError("config.validation_failed", params={"reason": "config_or_yaml"})
        return self


class ConfigValidateRequest(StrictModel):
    config: dict[str, Any] | None = None
    yaml: str | None = None
    expected_revision_id: int | None = None

    @model_validator(mode="after")
    def _one_content(self) -> ConfigValidateRequest:
        if (self.config is None) == (self.yaml is None):
            from .errors import AppError

            raise AppError("config.validation_failed", params={"reason": "config_or_yaml"})
        return self


class ConfigScheduleRequest(StrictModel):
    revision_id: int
    run_at: datetime


class ConfigApplyRequest(StrictModel):
    revision_id: int
    restart: bool = True


class ConfigRestoreRequest(StrictModel):
    note: str | None = Field(default=None, max_length=500)


class SystemSettingsUpdate(StrictModel):
    oxidized_api_url: str | None = None
    oxidized_container_name: str | None = None
    docker_proxy_url: str | None = None
    timezone: str | None = None
    activity_retention_days: int | None = Field(default=None, ge=0, le=3650)
    audit_retention_days: int | None = Field(default=None, ge=7, le=3650)
    poll_interval_seconds: int | None = Field(default=None, ge=15, le=300)
    log_tail_default: int | None = Field(default=None, ge=100, le=5000)
    config_backup_keep: int | None = Field(default=None, ge=0, le=500)
    password_min_length: int | None = Field(default=None, ge=8, le=128)
    password_require_complexity: bool | None = None
    password_history_count: int | None = Field(default=None, ge=0, le=24)
    login_max_failures_per_user: int | None = Field(default=None, ge=1, le=100)
    login_max_failures_per_ip: int | None = Field(default=None, ge=1, le=1000)
    login_window_minutes: int | None = Field(default=None, ge=1, le=1440)
    login_lockout_minutes: int | None = Field(default=None, ge=1, le=1440)
    ip_allowlist: str | None = Field(default=None, max_length=8192)
    notify_webhook_url: str | None = Field(default=None, max_length=2048)
    notify_on_failure: bool | None = None
    notify_stale_hours: int | None = Field(default=None, ge=0, le=720)
    retry_failed_enabled: bool | None = None
    retry_max_attempts: int | None = Field(default=None, ge=1, le=10)
    retry_base_minutes: int | None = Field(default=None, ge=1, le=1440)
    backup_batch_size: int | None = Field(default=None, ge=1, le=100)
    backup_batch_delay_seconds: int | None = Field(default=None, ge=0, le=300)
    health_alerts_enabled: bool | None = None
    health_disk_warn_percent: int | None = Field(default=None, ge=0, le=100)
    health_output_warn_mb: int | None = Field(default=None, ge=0, le=1_000_000)
    report_enabled: bool | None = None
    report_weekday: int | None = Field(default=None, ge=0, le=6)
    report_hour: int | None = Field(default=None, ge=0, le=23)
    report_keep: int | None = Field(default=None, ge=1, le=200)
    report_email_to: str | None = Field(default=None, max_length=500)
    health_alert_checks: int | None = Field(default=None, ge=1, le=24)
    smtp_host: str | None = Field(default=None, max_length=255)
    smtp_port: int | None = Field(default=None, ge=1, le=65535)
    smtp_user: str | None = Field(default=None, max_length=255)
    smtp_from: str | None = Field(default=None, max_length=255)
    smtp_tls: bool | None = None
    smtp_ssl: bool | None = None
    smtp_password: str | None = Field(default=None, max_length=512)
    clear_smtp_password: bool = False
    digest_enabled: bool | None = None
    digest_hour: int | None = Field(default=None, ge=0, le=23)
    export_enabled: bool | None = None
    export_interval_hours: int | None = Field(default=None, ge=1, le=720)
    site_name: str | None = Field(default=None, max_length=100)


NOTIFICATION_KINDS = ("webhook", "slack", "discord", "telegram")
NOTIFICATION_EVENTS = ("job.failed", "backup.stale", "config.changed", "backup.retry_exhausted")


class NotificationChannelCreate(StrictModel):
    name: str = Field(min_length=1, max_length=100)
    kind: Literal["webhook", "slack", "discord", "telegram"]
    enabled: bool = True
    events: list[str] = Field(default_factory=lambda: list(NOTIFICATION_EVENTS), max_length=10)
    digest_enabled: bool = False
    config: dict[str, Any] = Field(default_factory=dict)


class NotificationChannelUpdate(StrictModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    kind: Literal["webhook", "slack", "discord", "telegram"] | None = None
    enabled: bool | None = None
    events: list[str] | None = Field(default=None, max_length=10)
    digest_enabled: bool | None = None
    config: dict[str, Any] | None = None


class ConnectionTestRequest(StrictModel):
    target: Literal["oxidized", "docker"]


class SearchRequest(StrictModel):
    query: str = Field(min_length=1, max_length=200)


class BackupAllRequest(StrictModel):
    ids: list[int] | None = Field(default=None, max_length=1000)


class BackupScheduleCreate(StrictModel):
    group_name: str | None = Field(default=None, max_length=128)
    interval_minutes: int = Field(ge=15, le=10080)


class BackupScheduleUpdate(StrictModel):
    group_name: str | None = Field(default=None, max_length=128)
    interval_minutes: int | None = Field(default=None, ge=15, le=10080)
    enabled: bool | None = None


class MaintenanceWindowCreate(StrictModel):
    scope_type: Literal["node", "group", "global"] = "node"
    node_id: int | None = None
    group_name: str | None = Field(default=None, max_length=128)
    starts_at: datetime
    ends_at: datetime
    reason: str | None = Field(default=None, max_length=255)


class ConfigTemplateCreate(StrictModel):
    name: str = Field(min_length=1, max_length=100)
    scope_type: Literal["global", "group", "model"] = "global"
    scope_value: str | None = Field(default=None, max_length=128)
    content: str = Field(min_length=1, max_length=2_000_000)


class ConfigTemplateUpdate(StrictModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    scope_type: Literal["global", "group", "model"] | None = None
    scope_value: str | None = Field(default=None, max_length=128)
    content: str | None = Field(default=None, min_length=1, max_length=2_000_000)


class PreferenceUpdate(StrictModel):
    favorites: list[int] | None = Field(default=None, max_length=500)
    saved_filters: list[dict[str, Any]] | None = Field(default=None, max_length=50)


class ExportConfigPayload(StrictModel):
    kind: Literal["sftp", "s3"]
    interval_hours: int = Field(default=24, ge=1, le=720)
    enabled: bool = True
    config: dict[str, Any] = Field(default_factory=dict)


class SiteCoordinatesUpdate(StrictModel):
    site: str = Field(min_length=1, max_length=64)
    coordinates: str | None = Field(default=None, max_length=128)
    owner: str | None = Field(default=None, max_length=128)
    contact: str | None = Field(default=None, max_length=128)
    notes: str | None = Field(default=None, max_length=2000)
    reviewed: bool = False


class GoldenVersionRequest(StrictModel):
    oid: str | None = Field(default=None, max_length=128)


class ExportVerifyRequest(StrictModel):
    passphrase: str | None = Field(default=None, max_length=512)
    remote: bool = False


class JobPriorityRuleCreate(StrictModel):
    scope_type: Literal["group", "tag"] = "group"
    scope_key: str = Field(min_length=1, max_length=128)
    scope_value: str | None = Field(default=None, max_length=128)
    priority: int = Field(default=5, ge=1, le=10)
