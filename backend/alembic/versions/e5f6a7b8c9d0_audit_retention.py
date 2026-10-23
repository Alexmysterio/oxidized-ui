"""configurable audit retention"""
from __future__ import annotations
from typing import Union
from alembic import op
import sqlalchemy as sa
revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, None] = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column("system_settings", sa.Column("audit_retention_days", sa.Integer(), nullable=False, server_default="180"))

def downgrade() -> None:
    op.drop_column("system_settings", "audit_retention_days")
