"""golden versions"""
from __future__ import annotations
from typing import Union
from alembic import op
import sqlalchemy as sa

revision: str = "h8c9d0e1f2a3"
down_revision: Union[str, None] = "g7b8c9d0e1f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("nodes") as batch:
        batch.add_column(sa.Column("golden_oid", sa.String(length=128), nullable=True))
        batch.add_column(sa.Column("golden_at", sa.DateTime(), nullable=True))
    with op.batch_alter_table("site_locations") as batch:
        batch.add_column(sa.Column("owner", sa.String(length=128), nullable=True))
        batch.add_column(sa.Column("contact", sa.String(length=128), nullable=True))
        batch.add_column(sa.Column("notes", sa.Text(), nullable=True))
        batch.add_column(sa.Column("last_reviewed_at", sa.DateTime(), nullable=True))
        batch.alter_column("latitude", existing_type=sa.Float(), nullable=True)
        batch.alter_column("longitude", existing_type=sa.Float(), nullable=True)


def downgrade() -> None:
    with op.batch_alter_table("site_locations") as batch:
        batch.alter_column("longitude", existing_type=sa.Float(), nullable=False)
        batch.alter_column("latitude", existing_type=sa.Float(), nullable=False)
        batch.drop_column("last_reviewed_at")
        batch.drop_column("notes")
        batch.drop_column("contact")
        batch.drop_column("owner")
    with op.batch_alter_table("nodes") as batch:
        batch.drop_column("golden_at")
        batch.drop_column("golden_oid")
