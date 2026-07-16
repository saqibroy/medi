"""add versioned medical image intake decisions

Revision ID: 20260716_0008
Revises: 20260716_0007
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260716_0008"
down_revision: str | None = "20260716_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "scans",
        sa.Column("deidentification_status", sa.String(length=40), server_default="not_evaluated", nullable=False),
    )
    op.add_column("scans", sa.Column("deidentification_profile_version", sa.String(length=100), nullable=True))
    op.add_column("scans", sa.Column("deidentification_checked_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("scans", sa.Column("deidentification_evidence", sa.JSON(), nullable=True))

    op.execute(
        "UPDATE scans SET deidentification_status = 'synthetic', "
        "deidentification_profile_version = 'legacy-synthetic' "
        "WHERE source_format = 'synthetic'"
    )
    op.execute(
        "UPDATE scans SET ingestion_status = 'quarantined', "
        "ingestion_error = 'Legacy upload requires de-identification screening', "
        "deidentification_status = 'legacy_unverified', "
        "deidentification_profile_version = 'legacy-unverified', "
        "deidentification_evidence = '{\"decision\":\"legacy_unverified\",\"risk_flags\":[\"LegacyUploadNotScreened\"]}' "
        "WHERE source_format <> 'synthetic' AND ingestion_status = 'ready'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE scans SET ingestion_status = 'failed', "
        "ingestion_error = 'Scan unavailable until de-identification screening is restored' "
        "WHERE ingestion_status = 'quarantined'"
    )
    op.drop_column("scans", "deidentification_evidence")
    op.drop_column("scans", "deidentification_checked_at")
    op.drop_column("scans", "deidentification_profile_version")
    op.drop_column("scans", "deidentification_status")
