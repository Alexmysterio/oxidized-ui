"""password policy, lockout and allowlist

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-10-22 22:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("system_settings", sa.Column("password_min_length", sa.Integer(), nullable=False, server_default="12"))
    op.add_column(
        "system_settings",
        sa.Column("password_require_complexity", sa.Boolean(), nullable=False, server_default=sa.text("1")),
    )
    op.add_column("system_settings", sa.Column("password_history_count", sa.Integer(), nullable=False, server_default="5"))
    op.add_column(
        "system_settings",
        sa.Column("login_max_failures_per_user", sa.Integer(), nullable=False, server_default="5"),
    )
    op.add_column(
        "system_settings",
        sa.Column("login_max_failures_per_ip", sa.Integer(), nullable=False, server_default="20"),
    )
    op.add_column("system_settings", sa.Column("login_window_minutes", sa.Integer(), nullable=False, server_default="15"))
    op.add_column(
        "system_settings",
        sa.Column("login_lockout_minutes", sa.Integer(), nullable=False, server_default="30"),
    )
    op.add_column("system_settings", sa.Column("ip_allowlist", sa.Text(), nullable=False, server_default=""))
    op.create_table(
        "password_history",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_password_history_user", "password_history", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_password_history_user", table_name="password_history")
    op.drop_table("password_history")
    for column in (
        "ip_allowlist",
        "login_lockout_minutes",
        "login_window_minutes",
        "login_max_failures_per_ip",
        "login_max_failures_per_user",
        "password_history_count",
        "password_require_complexity",
        "password_min_length",
    ):
        op.drop_column("system_settings", column)
