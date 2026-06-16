"""add needs_changes review status

Revision ID: 20260616_0004
Revises: 20260616_0003
Create Date: 2026-06-16
"""

from collections.abc import Sequence

from alembic import op


revision: str = "20260616_0004"
down_revision: str | None = "20260616_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("annotations") as batch_op:
        batch_op.drop_constraint("ck_annotation_review_status", type_="check")
        batch_op.create_check_constraint(
            "ck_annotation_review_status",
            "review_status IN ('pending', 'approved', 'rejected', 'needs_changes')",
        )


def downgrade() -> None:
    with op.batch_alter_table("annotations") as batch_op:
        batch_op.drop_constraint("ck_annotation_review_status", type_="check")
        batch_op.create_check_constraint(
            "ck_annotation_review_status",
            "review_status IN ('pending', 'approved', 'rejected')",
        )
