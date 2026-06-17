"""add annotation assignment owner

Revision ID: 20260617_0006
Revises: 20260616_0005
Create Date: 2026-06-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260617_0006"
down_revision: str | None = "20260616_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("annotations") as batch_op:
        batch_op.add_column(sa.Column("assigned_to_user_id", sa.Uuid(), nullable=True))
        batch_op.create_foreign_key("fk_annotations_assigned_to_user_id_users", "users", ["assigned_to_user_id"], ["id"])
        batch_op.create_index(op.f("ix_annotations_assigned_to_user_id"), ["assigned_to_user_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("annotations") as batch_op:
        batch_op.drop_index(op.f("ix_annotations_assigned_to_user_id"))
        batch_op.drop_constraint("fk_annotations_assigned_to_user_id_users", type_="foreignkey")
        batch_op.drop_column("assigned_to_user_id")
