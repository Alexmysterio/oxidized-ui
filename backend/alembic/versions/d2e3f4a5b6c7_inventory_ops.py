"""tags, node templates, node facts, job priorities, pacing, health and reports

Revision ID: d2e3f4a5b6c7
Revises: c1d2e3f4a5b6
"""
from __future__ import annotations

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "d2e3f4a5b6c7"
down_revision: Union[str, None] = "c1d2e3f4a5b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("nodes", sa.Column("tags", sa.JSON(), nullable=True))
    op.add_column("jobs", sa.Column("priority", sa.Integer(), nullable=False, server_default="5"))

    for column in (
        sa.Column("backup_batch_size", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("backup_batch_delay_seconds", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("health_alerts_enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("health_disk_warn_percent", sa.Integer(), nullable=False, server_default="85"),
        sa.Column("health_output_warn_mb", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("report_enabled", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("report_weekday", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("report_hour", sa.Integer(), nullable=False, server_default="8"),
        sa.Column("report_last_run_at", sa.DateTime(), nullable=True),
    ):
        op.add_column("system_settings", column)

    op.create_table(
        "node_templates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("group_name", sa.String(length=128), nullable=True),
        sa.Column("input", sa.String(length=128), nullable=True),
        sa.Column("port", sa.Integer(), nullable=True),
        sa.Column("username", sa.String(length=128), nullable=True),
        sa.Column("output", sa.String(length=128), nullable=True),
        sa.Column("prompt", sa.String(length=512), nullable=True),
        sa.Column("timeout_seconds", sa.Integer(), nullable=True),
        sa.Column("vars", sa.JSON(), nullable=True),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_node_templates_name"),
    )

    op.create_table(
        "node_facts",
        sa.Column("node_id", sa.Integer(), nullable=False),
        sa.Column("serial", sa.String(length=128), nullable=True),
        sa.Column("os_version", sa.String(length=255), nullable=True),
        sa.Column("uptime", sa.String(length=255), nullable=True),
        sa.Column("collected_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["node_id"], ["nodes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("node_id"),
    )

    op.create_table(
        "job_priority_rules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("scope_type", sa.String(length=16), nullable=False, server_default="group"),
        sa.Column("scope_key", sa.String(length=128), nullable=False),
        sa.Column("scope_value", sa.String(length=128), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("scope_type", "scope_key", "scope_value", name="uq_job_priority_rule"),
    )


def downgrade() -> None:
    op.drop_table("job_priority_rules")
    op.drop_table("node_facts")
    op.drop_table("node_templates")
    for name in (
        "report_last_run_at",
        "report_hour",
        "report_weekday",
        "report_enabled",
        "health_output_warn_mb",
        "health_disk_warn_percent",
        "health_alerts_enabled",
        "backup_batch_delay_seconds",
        "backup_batch_size",
    ):
        op.drop_column("system_settings", name)
    op.drop_column("jobs", "priority")
    op.drop_column("nodes", "tags")
