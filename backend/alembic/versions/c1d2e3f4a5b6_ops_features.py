"""retries, maintenance windows, compliance, scoped access, digests, exports

Revision ID: c1d2e3f4a5b6
Revises: b8c9d0e1f2a3
"""
from __future__ import annotations

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "c1d2e3f4a5b6"
down_revision: Union[str, None] = "b8c9d0e1f2a3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("scope_groups", sa.JSON(), nullable=True))

    for name, column in (
        ("retry_failed_enabled", sa.Column("retry_failed_enabled", sa.Boolean(), nullable=False, server_default=sa.text("1"))),
        ("retry_max_attempts", sa.Column("retry_max_attempts", sa.Integer(), nullable=False, server_default="3")),
        ("retry_base_minutes", sa.Column("retry_base_minutes", sa.Integer(), nullable=False, server_default="15")),
        ("digest_enabled", sa.Column("digest_enabled", sa.Boolean(), nullable=False, server_default=sa.text("0"))),
        ("digest_hour", sa.Column("digest_hour", sa.Integer(), nullable=False, server_default="8")),
        ("export_enabled", sa.Column("export_enabled", sa.Boolean(), nullable=False, server_default=sa.text("0"))),
        ("export_interval_hours", sa.Column("export_interval_hours", sa.Integer(), nullable=False, server_default="24")),
        ("export_config_ciphertext", sa.Column("export_config_ciphertext", sa.Text(), nullable=True)),
        ("export_next_run_at", sa.Column("export_next_run_at", sa.DateTime(), nullable=True)),
        ("export_last_run_at", sa.Column("export_last_run_at", sa.DateTime(), nullable=True)),
        ("export_last_status", sa.Column("export_last_status", sa.String(length=32), nullable=True)),
        ("export_last_error", sa.Column("export_last_error", sa.String(length=255), nullable=True)),
    ):
        op.add_column("system_settings", column)

    op.add_column(
        "notification_channels",
        sa.Column("digest_enabled", sa.Boolean(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column("notification_channels", sa.Column("last_digest_at", sa.DateTime(), nullable=True))

    op.create_table(
        "node_retries",
        sa.Column("node_id", sa.Integer(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(), nullable=False),
        sa.Column("failure_at", sa.DateTime(), nullable=True),
        sa.Column("exhausted_notified", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_error", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["node_id"], ["nodes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("node_id"),
    )
    op.create_index("ix_node_retries_due", "node_retries", ["next_attempt_at"], unique=False)

    op.create_table(
        "node_config_state",
        sa.Column("node_id", sa.Integer(), nullable=False),
        sa.Column("last_mtime", sa.DateTime(), nullable=True),
        sa.Column("content_sha256", sa.String(length=64), nullable=True),
        sa.Column("last_changed_at", sa.DateTime(), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["node_id"], ["nodes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("node_id"),
    )

    op.create_table(
        "maintenance_windows",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("scope_type", sa.String(length=16), nullable=False, server_default="node"),
        sa.Column("node_id", sa.Integer(), nullable=True),
        sa.Column("group_name", sa.String(length=128), nullable=True),
        sa.Column("starts_at", sa.DateTime(), nullable=False),
        sa.Column("ends_at", sa.DateTime(), nullable=False),
        sa.Column("reason", sa.String(length=255), nullable=True),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["node_id"], ["nodes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_maintenance_window_span", "maintenance_windows", ["starts_at", "ends_at"], unique=False)

    op.create_table(
        "config_templates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("scope_type", sa.String(length=16), nullable=False, server_default="global"),
        sa.Column("scope_value", sa.String(length=128), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_config_templates_name"),
    )

    op.create_table(
        "user_preferences",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("favorites", sa.JSON(), nullable=False),
        sa.Column("saved_filters", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )


def downgrade() -> None:
    op.drop_table("user_preferences")
    op.drop_table("config_templates")
    op.drop_index("ix_maintenance_window_span", table_name="maintenance_windows")
    op.drop_table("maintenance_windows")
    op.drop_table("node_config_state")
    op.drop_index("ix_node_retries_due", table_name="node_retries")
    op.drop_table("node_retries")
    op.drop_column("notification_channels", "last_digest_at")
    op.drop_column("notification_channels", "digest_enabled")
    for name in (
        "export_last_error",
        "export_last_status",
        "export_last_run_at",
        "export_next_run_at",
        "export_config_ciphertext",
        "export_interval_hours",
        "export_enabled",
        "digest_hour",
        "digest_enabled",
        "retry_base_minutes",
        "retry_max_attempts",
        "retry_failed_enabled",
    ):
        op.drop_column("system_settings", name)
    op.drop_column("users", "scope_groups")
