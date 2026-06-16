"""add segmentation mask metadata

Revision ID: 20260616_0005
Revises: 20260616_0004
Create Date: 2026-06-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260616_0005"
down_revision: str | None = "20260616_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "segmentation_masks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("annotation_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("scan_id", sa.Uuid(), nullable=False),
        sa.Column("slice_index", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.String(length=700), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("encoding", sa.String(length=40), server_default="png_binary", nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("updated_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("height > 0", name="ck_segmentation_mask_height_positive"),
        sa.CheckConstraint("width > 0", name="ck_segmentation_mask_width_positive"),
        sa.ForeignKeyConstraint(["annotation_id"], ["annotations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["scan_id"], ["scans.id"]),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("annotation_id", "slice_index", name="uq_segmentation_masks_annotation_slice"),
    )
    op.create_index(op.f("ix_segmentation_masks_annotation_id"), "segmentation_masks", ["annotation_id"], unique=False)
    op.create_index(op.f("ix_segmentation_masks_project_id"), "segmentation_masks", ["project_id"], unique=False)
    op.create_index(op.f("ix_segmentation_masks_scan_id"), "segmentation_masks", ["scan_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_segmentation_masks_scan_id"), table_name="segmentation_masks")
    op.drop_index(op.f("ix_segmentation_masks_project_id"), table_name="segmentation_masks")
    op.drop_index(op.f("ix_segmentation_masks_annotation_id"), table_name="segmentation_masks")
    op.drop_table("segmentation_masks")
