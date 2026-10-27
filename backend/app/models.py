from __future__ import annotations

from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base
from .timeutil import UTCDateTime, utcnow

ROLES = ("admin", "operator", "viewer")
THEMES = ("light", "dark", "system")
NODE_STATUSES = ("success", "no_connection", "fail", "timelimit", "unknown")
JOB_KINDS = (
    "backup_node",
    "backup_all",
    "backup_export",
    "facts_collect",
    "report",
    "oxidized_reload",
    "oxidized_restart",
    "config_apply",
)
JOB_STATUSES = ("queued", "running", "succeeded", "failed", "cancelled")
REVISION_STATUSES = ("draft", "applied", "superseded", "discarded", "rolled_back")
REVISION_ORIGINS = ("bootstrap", "form", "yaml", "groups", "rollback", "external_import")


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('admin','operator','viewer')", name="ck_users_role"),
        CheckConstraint("theme IN ('light','dark','system')", name="ck_users_theme"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), nullable=False)
    username_key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    avatar_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    scope_groups: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False, default="viewer")
    language: Mapped[str] = mapped_column(String(16), nullable=False, default="es")
    theme: Mapped[str] = mapped_column(String(16), nullable=False, default="system")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[Any] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    updated_at: Mapped[Any] = mapped_column(UTCDateTime, nullable=False, default=utcnow, onupdate=utcnow)
    last_login_at: Mapped[Any | None] = mapped_column(UTCDateTime, nullable=True)
    password_changed_at: Mapped[Any] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    mfa_secret_ciphertext: Mapped[str | None] = mapped_column(Text, nullable=True)
    mfa_enabled_at: Mapped[Any | None] = mapped_column(UTCDateTime, nullable=True)


class UserSession(Base):
    __tablename__ = "sessions"
    __table_args__ = (
        Index("ix_sessions_user_id", "user_id"),
        Index("ix_sessions_expires_at", "expires_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    created_at: Mapped[Any] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    last_seen_at: Mapped[Any] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    expires_at: Mapped[Any] = mapped_column(UTCDateTime, nullable=False)
    revoked_at: Mapped[Any | None] = mapped_column(UTCDateTime, nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)


class PasswordHistory(Base):
    __tablename__ = "password_history"
    __table_args__ = (Index("ix_password_history_user", "user_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[Any] = mapped_column(UTCDateTime, nullable=False, default=utcnow)


class MfaRecoveryCode(Base):
    __tablename__ = "mfa_recovery_codes"
    __table_args__ = (Index("ix_mfa_recovery_user", "user_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    code_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[Any] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    used_at: Mapped[Any | None] = mapped_column(UTCDateTime, nullable=True)


class MfaChallenge(Base):
    __tablename__ = "mfa_challenges"
    __table_args__ = (
        Index("ix_mfa_challenge_expires", "expires_at"),
        Index("ix_mfa_challenge_user", "user_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    created_at: Mapped[Any] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    expires_at: Mapped[Any] = mapped_column(UTCDateTime, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    consumed_at: Mapped[Any | None] = mapped_column(UTCDateTime, nullable=True)


class LoginAttempt(Base):
    __tablename__ = "login_attempts"
    __table_args__ = (
        Index("ix_login_attempts_ip_created", "ip", "created_at"),
        Index("ix_login_attempts_user_created", "username_key", "created_at"),
        Index("ix_login_attempts_created", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username_key: Mapped[str] = mapped_column(String(64), nullable=False)
    ip: Mapped[str] = mapped_column(String(64), nullable=False)
    succeeded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[Any] = mapped_column(UTCDateTime, nullable=False, default=utcnow)


class Node(Base):
    __tablename__ = "nodes"
    __table_args__ = (
        UniqueConstraint("name_key", name="uq_nodes_name_key"),
        Index("ix_nodes_group_name", "group_name"),
        Index("ix_nodes_model", "model"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(253), nullable=False)
    name_key: Mapped[str] = mapped_column(String(253), nullable=False)
    address: Mapped[str | None] = mapped_column(String(253), nullable=True)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    group_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    input: Mapped[str | None] = mapped_column(String(128), nullable=True)
    port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    username: Mapped[str | None] = mapped_column(String(128), nullable=True)
    password_ciphertext: Mapped[str | None] = mapped_column(Text, nullable=True)
    enable_ciphertext: Mapped[str | None] = mapped_column(Text, nullable=True)
    vars_ciphertext: Mapped[str | None] = mapped_column(Text, nullable=True)
    output: Mapped[str | None] = mapped_column(String(128), nullable=True)
    prompt: Mapped[str | None] = mapped_column(String(512), nullable=True)
    timeout_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tags: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[Any] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    updated_at: Mapped[Any] = mapped_column(UTCDateTime, nullable=False, default=utcnow, onupdate=utcnow)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


class NodeStatusCache(Base):
    __tablename__ = "node_status_cache"

    node_id: Mapped[int] = mapped_column(ForeignKey("nodes.id", ondelete="CASCADE"), primary_key=True)
    status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_started_at: Mapped[Any | None] = mapped_column(UTCDateTime, nullable=True)
    last_finished_at: Mapped[Any | None] = mapped_column(UTCDateTime, nullable=True)
    last_success_at: Mapped[Any | None] = mapped_column(UTCDateTime, nullable=True)
    last_failure_at: Mapped[Any | None] = mapped_column(UTCDateTime, nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    oxidized_mtime: Mapped[Any | None] = mapped_column(UTCDateTime, nullable=True)
    observed_at: Mapped[Any] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    raw_last_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        Index("ix_jobs_status_created", "status", "created_at"),
        Index("ix_jobs_kind_created", "kind", "created_at"),
        Index("ix_jobs_node_id", "node_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued")
    node_id: Mapped[int | None] = mapped_column(ForeignKey("nodes.id", ondelete="SET NULL"), nullable=True)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    progress_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    progress_done: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error_params: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[Any] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    started_at: Mapped[Any | None] = mapped_column(UTCDateTime, nullable=True)
    finished_at: Mapped[Any | None] = mapped_column(UTCDateTime, nullable=True)


class BackupRun(Base):
    __tablename__ = "backup_runs"
    __table_args__ = (
        UniqueConstraint("dedupe_key", name="uq_backup_runs_dedupe"),
        Index("ix_backup_runs_finished", "finished_at"),
        Index("ix_backup_runs_node_finished", "node_id", "finished_at"),
        Index("ix_backup_runs_status_finished", "status", "finished_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    node_id: Mapped[int | None] = mapped_column(ForeignKey("nodes.id", ondelete="SET NULL"), nullable=True)
    node_name: Mapped[str] = mapped_column(String(253), nullable=False)
    group_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    started_at: Mapped[Any] = mapped_column(UTCDateTime, nullable=False)
    finished_at: Mapped[Any | None] = mapped_column(UTCDateTime, nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    trigger: Mapped[str] = mapped_column(String(16), nullable=False, default="observed")
    job_id: Mapped[int | None] = mapped_column(ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True)
    dedupe_key: Mapped[str] = mapped_column(String(64), nullable=False)
    observed_at: Mapped[Any] = mapped_column(UTCDateTime, nullable=False, default=utcnow)


class ConfigRevision(Base):
    __tablename__ = "config_revisions"
    __table_args__ = (
        Index("ix_config_revisions_status_created", "status", "created_at"),
        Index("ix_config_revisions_created", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("config_revisions.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    origin: Mapped[str] = mapped_column(String(32), nullable=False, default="form")
    config_ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    yaml_ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    config_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    yaml_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[Any] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    applied_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    applied_at: Mapped[Any | None] = mapped_column(UTCDateTime, nullable=True)
    file_written_at: Mapped[Any | None] = mapped_column(UTCDateTime, nullable=True)
    file_written_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)


class ConfigFileSnapshot(Base):
    __tablename__ = "config_file_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    revision_id: Mapped[int | None] = mapped_column(
        ForeignKey("config_revisions.id", ondelete="SET NULL"), nullable=True
    )
    reason: Mapped[str] = mapped_column(String(32), nullable=False)
    yaml_ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    captured_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    captured_at: Mapped[Any] = mapped_column(UTCDateTime, nullable=False, default=utcnow)


class ApiToken(Base):
    __tablename__ = "api_tokens"
    __table_args__ = (Index("ix_api_tokens_user", "user_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    prefix: Mapped[str] = mapped_column(String(16), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False, default="viewer")
    expires_at: Mapped[Any | None] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[Any] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    last_used_at: Mapped[Any | None] = mapped_column(UTCDateTime, nullable=True)
    revoked_at: Mapped[Any | None] = mapped_column(UTCDateTime, nullable=True)


class BackupSchedule(Base):
    __tablename__ = "backup_schedules"
    __table_args__ = (Index("ix_backup_schedule_due", "enabled", "next_run_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    group_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    interval_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=1440)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    next_run_at: Mapped[Any] = mapped_column(UTCDateTime, nullable=False)
    last_run_at: Mapped[Any | None] = mapped_column(UTCDateTime, nullable=True)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[Any] = mapped_column(UTCDateTime, nullable=False, default=utcnow)


class ScheduledConfigApply(Base):
    __tablename__ = "scheduled_config_applies"
    __table_args__ = (Index("ix_scheduled_config_run", "status", "run_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    revision_id: Mapped[int | None] = mapped_column(
        ForeignKey("config_revisions.id", ondelete="SET NULL"), nullable=True
    )
    run_at: Mapped[Any] = mapped_column(UTCDateTime, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    job_id: Mapped[int | None] = mapped_column(ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[Any] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    started_at: Mapped[Any | None] = mapped_column(UTCDateTime, nullable=True)
    finished_at: Mapped[Any | None] = mapped_column(UTCDateTime, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)


class SystemState(Base):
    __tablename__ = "system_state"
    __table_args__ = (CheckConstraint("id = 1", name="ck_system_state_singleton"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    setup_completed_at: Mapped[Any | None] = mapped_column(UTCDateTime, nullable=True)
    initialized_at: Mapped[Any] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    app_instance_id: Mapped[str] = mapped_column(String(36), nullable=False)
    active_revision_id: Mapped[int | None] = mapped_column(
        ForeignKey("config_revisions.id", ondelete="SET NULL"), nullable=True
    )
    active_file_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    drift_detected_at: Mapped[Any | None] = mapped_column(UTCDateTime, nullable=True)
    last_oxidized_seen_at: Mapped[Any | None] = mapped_column(UTCDateTime, nullable=True)
    last_apply_error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)


class SystemSettings(Base):
    __tablename__ = "system_settings"
    __table_args__ = (CheckConstraint("id = 1", name="ck_system_settings_singleton"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    oxidized_api_url: Mapped[str] = mapped_column(String(512), nullable=False)
    oxidized_container_name: Mapped[str] = mapped_column(String(128), nullable=False)
    docker_proxy_url: Mapped[str] = mapped_column(String(512), nullable=False)
    timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    activity_retention_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    audit_retention_days: Mapped[int] = mapped_column(Integer, nullable=False, default=180)
    poll_interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    log_tail_default: Mapped[int] = mapped_column(Integer, nullable=False, default=500)
    config_backup_keep: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    password_min_length: Mapped[int] = mapped_column(Integer, nullable=False, default=12)
    password_require_complexity: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    password_history_count: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    login_max_failures_per_user: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    login_max_failures_per_ip: Mapped[int] = mapped_column(Integer, nullable=False, default=20)
    login_window_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=15)
    login_lockout_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    ip_allowlist: Mapped[str] = mapped_column(Text, nullable=False, default="")
    notify_webhook_url: Mapped[str] = mapped_column(Text, nullable=False, default="")
    notify_on_failure: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notify_stale_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    retry_failed_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    retry_max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    retry_base_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=15)
    digest_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    digest_hour: Mapped[int] = mapped_column(Integer, nullable=False, default=8)
    export_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    export_interval_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=24)
    export_config_ciphertext: Mapped[str | None] = mapped_column(Text, nullable=True)
    export_next_run_at: Mapped[Any | None] = mapped_column(UTCDateTime, nullable=True)
    export_last_run_at: Mapped[Any | None] = mapped_column(UTCDateTime, nullable=True)
    export_last_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    export_last_error: Mapped[str | None] = mapped_column(String(255), nullable=True)
    backup_batch_size: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    backup_batch_delay_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    health_alerts_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    health_disk_warn_percent: Mapped[int] = mapped_column(Integer, nullable=False, default=85)
    health_output_warn_mb: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    report_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    report_weekday: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    report_hour: Mapped[int] = mapped_column(Integer, nullable=False, default=8)
    report_last_run_at: Mapped[Any | None] = mapped_column(UTCDateTime, nullable=True)
    site_name: Mapped[str] = mapped_column(String(100), nullable=False, default="Oxidized UI")
    logo_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_at: Mapped[Any] = mapped_column(UTCDateTime, nullable=False, default=utcnow, onupdate=utcnow)


class NotificationChannel(Base):
    __tablename__ = "notification_channels"
    __table_args__ = (Index("ix_notification_channels_enabled", "enabled"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    config_ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    events: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    digest_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_digest_at: Mapped[Any | None] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[Any] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    updated_at: Mapped[Any] = mapped_column(UTCDateTime, nullable=False, default=utcnow, onupdate=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_created", "created_at"),
        Index("ix_audit_actor_created", "actor_user_id", "created_at"),
        Index("ix_audit_action_created", "action_code", "created_at"),
        Index("ix_audit_target", "target_type", "target_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    actor_username: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_role: Mapped[str] = mapped_column(String(16), nullable=False)
    action_code: Mapped[str] = mapped_column(String(128), nullable=False)
    action_params: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    target_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    target_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[Any] = mapped_column(UTCDateTime, nullable=False, default=utcnow)


class NodeRetry(Base):
    __tablename__ = "node_retries"
    __table_args__ = (Index("ix_node_retries_due", "next_attempt_at"),)

    node_id: Mapped[int] = mapped_column(ForeignKey("nodes.id", ondelete="CASCADE"), primary_key=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at: Mapped[Any] = mapped_column(UTCDateTime, nullable=False)
    failure_at: Mapped[Any | None] = mapped_column(UTCDateTime, nullable=True)
    exhausted_notified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_error: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[Any] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    updated_at: Mapped[Any] = mapped_column(UTCDateTime, nullable=False, default=utcnow, onupdate=utcnow)


class NodeConfigState(Base):
    __tablename__ = "node_config_state"

    node_id: Mapped[int] = mapped_column(ForeignKey("nodes.id", ondelete="CASCADE"), primary_key=True)
    last_mtime: Mapped[Any | None] = mapped_column(UTCDateTime, nullable=True)
    content_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_changed_at: Mapped[Any | None] = mapped_column(UTCDateTime, nullable=True)
    last_checked_at: Mapped[Any | None] = mapped_column(UTCDateTime, nullable=True)


class MaintenanceWindow(Base):
    __tablename__ = "maintenance_windows"
    __table_args__ = (Index("ix_maintenance_window_span", "starts_at", "ends_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scope_type: Mapped[str] = mapped_column(String(16), nullable=False, default="node")
    node_id: Mapped[int | None] = mapped_column(ForeignKey("nodes.id", ondelete="CASCADE"), nullable=True)
    group_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    starts_at: Mapped[Any] = mapped_column(UTCDateTime, nullable=False)
    ends_at: Mapped[Any] = mapped_column(UTCDateTime, nullable=False)
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[Any] = mapped_column(UTCDateTime, nullable=False, default=utcnow)


class ConfigTemplate(Base):
    __tablename__ = "config_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    scope_type: Mapped[str] = mapped_column(String(16), nullable=False, default="global")
    scope_value: Mapped[str | None] = mapped_column(String(128), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[Any] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    updated_at: Mapped[Any] = mapped_column(UTCDateTime, nullable=False, default=utcnow, onupdate=utcnow)


class UserPreference(Base):
    __tablename__ = "user_preferences"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    favorites: Mapped[list[int]] = mapped_column(JSON, nullable=False, default=list)
    saved_filters: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    updated_at: Mapped[Any] = mapped_column(UTCDateTime, nullable=False, default=utcnow, onupdate=utcnow)


class NodeTemplate(Base):
    __tablename__ = "node_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    group_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    input: Mapped[str | None] = mapped_column(String(128), nullable=True)
    port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    username: Mapped[str | None] = mapped_column(String(128), nullable=True)
    output: Mapped[str | None] = mapped_column(String(128), nullable=True)
    prompt: Mapped[str | None] = mapped_column(String(512), nullable=True)
    timeout_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    vars: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[Any] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    updated_at: Mapped[Any] = mapped_column(UTCDateTime, nullable=False, default=utcnow, onupdate=utcnow)


class NodeFacts(Base):
    __tablename__ = "node_facts"

    node_id: Mapped[int] = mapped_column(ForeignKey("nodes.id", ondelete="CASCADE"), primary_key=True)
    serial: Mapped[str | None] = mapped_column(String(128), nullable=True)
    os_version: Mapped[str | None] = mapped_column(String(255), nullable=True)
    uptime: Mapped[str | None] = mapped_column(String(255), nullable=True)
    collected_at: Mapped[Any] = mapped_column(UTCDateTime, nullable=False, default=utcnow)


class JobPriorityRule(Base):
    __tablename__ = "job_priority_rules"
    __table_args__ = (
        UniqueConstraint("scope_type", "scope_key", "scope_value", name="uq_job_priority_rule"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scope_type: Mapped[str] = mapped_column(String(16), nullable=False, default="group")
    scope_key: Mapped[str] = mapped_column(String(128), nullable=False)
    scope_value: Mapped[str | None] = mapped_column(String(128), nullable=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    created_at: Mapped[Any] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
