"""notification webhook settings

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
"""
from __future__ import annotations
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, None] = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column("system_settings", sa.Column("notify_webhook_url", sa.Text(), nullable=False, server_default=""))
    op.add_column("system_settings", sa.Column("notify_on_failure", sa.Boolean(), nullable=False, server_default=sa.text("1")))
    op.add_column("system_settings", sa.Column("notify_stale_hours", sa.Integer(), nullable=False, server_default="0"))

def downgrade() -> None:
    for column in ("notify_stale_hours", "notify_on_failure", "notify_webhook_url"):
        op.drop_column("system_settings", column)
