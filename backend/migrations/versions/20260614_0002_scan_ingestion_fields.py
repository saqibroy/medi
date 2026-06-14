"""add scan ingestion fields

Revision ID: 20260614_0002
Revises: 20260614_0001
Create Date: 2026-06-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260614_0002"
down_revision: str | None = "20260614_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("scans", sa.Column("storage_key", sa.String(length=700), nullable=True))
    op.add_column("scans", sa.Column("source_format", sa.String(length=40), server_default="synthetic", nullable=False))
    op.add_column("scans", sa.Column("ingestion_status", sa.String(length=40), server_default="ready", nullable=False))
    op.add_column("scans", sa.Column("ingestion_error", sa.String(length=1000), nullable=True))
    op.add_column("scans", sa.Column("metadata", sa.JSON(), nullable=True))
    op.add_column("scans", sa.Column("width", sa.Integer(), nullable=True))
    op.add_column("scans", sa.Column("height", sa.Integer(), nullable=True))
    op.add_column("scans", sa.Column("depth", sa.Integer(), nullable=True))
    op.add_column("scans", sa.Column("spacing", sa.JSON(), nullable=True))
    op.add_column("scans", sa.Column("window_center", sa.Float(), nullable=True))
    op.add_column("scans", sa.Column("window_width", sa.Float(), nullable=True))
    op.execute("UPDATE scans SET storage_key = file_path, depth = num_slices, width = 512, height = 512 WHERE storage_key IS NULL")


def downgrade() -> None:
    op.drop_column("scans", "window_width")
    op.drop_column("scans", "window_center")
    op.drop_column("scans", "spacing")
    op.drop_column("scans", "depth")
    op.drop_column("scans", "height")
    op.drop_column("scans", "width")
    op.drop_column("scans", "metadata")
    op.drop_column("scans", "ingestion_error")
    op.drop_column("scans", "ingestion_status")
    op.drop_column("scans", "source_format")
    op.drop_column("scans", "storage_key")
