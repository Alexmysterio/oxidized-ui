"""backup schedules"""
from __future__ import annotations
from typing import Union
from alembic import op
import sqlalchemy as sa
revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, None] = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table(
        "backup_schedules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("group_name", sa.String(length=128), nullable=True),
        sa.Column("interval_minutes", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("next_run_at", sa.DateTime(), nullable=False),
        sa.Column("last_run_at", sa.DateTime(), nullable=True),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_backup_schedule_due", "backup_schedules", ["enabled", "next_run_at"], unique=False)

def downgrade() -> None:
    op.drop_index("ix_backup_schedule_due", table_name="backup_schedules")
    op.drop_table("backup_schedules")
