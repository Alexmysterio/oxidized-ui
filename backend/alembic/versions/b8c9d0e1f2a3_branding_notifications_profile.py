"""branding, notification channels and user profile fields

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
"""
from __future__ import annotations

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "b8c9d0e1f2a3"
down_revision: Union[str, None] = "a7b8c9d0e1f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("full_name", sa.String(length=128), nullable=True))
    op.add_column("users", sa.Column("email", sa.String(length=254), nullable=True))
    op.add_column("users", sa.Column("avatar_filename", sa.String(length=255), nullable=True))
    op.add_column(
        "system_settings",
        sa.Column("site_name", sa.String(length=100), nullable=False, server_default="Oxidized UI"),
    )
    op.add_column("system_settings", sa.Column("logo_filename", sa.String(length=255), nullable=True))
    op.create_table(
        "notification_channels",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("config_ciphertext", sa.Text(), nullable=False),
        sa.Column("events", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_notification_channels_enabled",
        "notification_channels",
        ["enabled"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_notification_channels_enabled", table_name="notification_channels")
    op.drop_table("notification_channels")
    op.drop_column("system_settings", "logo_filename")
    op.drop_column("system_settings", "site_name")
    op.drop_column("users", "avatar_filename")
    op.drop_column("users", "email")
    op.drop_column("users", "full_name")
