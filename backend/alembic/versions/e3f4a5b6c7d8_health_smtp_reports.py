"""health history, SMTP and report retention

Revision ID: e3f4a5b6c7d8
Revises: d2e3f4a5b6c7
"""
from __future__ import annotations

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "e3f4a5b6c7d8"
down_revision: Union[str, None] = "d2e3f4a5b6c7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for column in (
        sa.Column("health_alert_checks", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("report_keep", sa.Integer(), nullable=False, server_default="12"),
        sa.Column("report_email_to", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("smtp_host", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("smtp_port", sa.Integer(), nullable=False, server_default="587"),
        sa.Column("smtp_user", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("smtp_password_ciphertext", sa.Text(), nullable=True),
        sa.Column("smtp_from", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("smtp_tls", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("smtp_ssl", sa.Boolean(), nullable=False, server_default=sa.text("0")),
    ):
        op.add_column("system_settings", column)

    op.create_table(
        "health_samples",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("observed_at", sa.DateTime(), nullable=False),
        sa.Column("disk_percent", sa.Float(), nullable=False, server_default="0"),
        sa.Column("db_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("queue_depth", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("nodes", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_health_samples_observed", "health_samples", ["observed_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_health_samples_observed", table_name="health_samples")
    op.drop_table("health_samples")
    for name in (
        "smtp_ssl",
        "smtp_tls",
        "smtp_from",
        "smtp_password_ciphertext",
        "smtp_user",
        "smtp_port",
        "smtp_host",
        "report_email_to",
        "report_keep",
        "health_alert_checks",
    ):
        op.drop_column("system_settings", name)
