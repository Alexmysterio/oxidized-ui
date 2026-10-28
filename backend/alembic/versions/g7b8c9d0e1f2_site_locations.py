"""site locations"""
from __future__ import annotations
from typing import Union
from alembic import op
import sqlalchemy as sa

revision: str = "g7b8c9d0e1f2"
down_revision: Union[str, None] = "e3f4a5b6c7d8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "site_locations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("name_key", sa.String(length=64), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by_id", sa.Integer(), nullable=True),
        sa.CheckConstraint("latitude >= -90 AND latitude <= 90", name="ck_site_latitude"),
        sa.CheckConstraint("longitude >= -180 AND longitude <= 180", name="ck_site_longitude"),
        sa.ForeignKeyConstraint(["updated_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name_key", name="uq_site_locations_name_key"),
    )


def downgrade() -> None:
    op.drop_table("site_locations")
