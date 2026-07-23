"""add organization-wide governed deletion controls

Revision ID: 20260723_0017
Revises: 20260723_0016
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260723_0017"
down_revision: str | None = "20260723_0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _replace_deletion_scope_constraint(values: str) -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        op.execute("DROP TRIGGER IF EXISTS data_deletion_requests_no_update")
        op.execute("DROP TRIGGER IF EXISTS data_deletion_requests_no_delete")
    with op.batch_alter_table("data_deletion_requests") as batch_op:
        batch_op.drop_constraint("ck_data_deletion_request_scope", type_="check")
        batch_op.create_check_constraint(
            "ck_data_deletion_request_scope",
            f"scope_type IN ({values})",
        )
    if dialect == "sqlite":
        for operation in ("UPDATE", "DELETE"):
            op.execute(
                f"""
                CREATE TRIGGER data_deletion_requests_no_{operation.lower()}
                BEFORE {operation} ON data_deletion_requests
                BEGIN
                    SELECT RAISE(ABORT, 'data governance records are append-only');
                END
                """
            )


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column(
            "lifecycle_status",
            sa.String(length=30),
            sa.CheckConstraint(
                "lifecycle_status IN ('active', 'deletion_in_progress', 'deleted')",
                name="ck_organization_lifecycle_status",
            ),
            server_default="active",
            nullable=False,
        ),
    )
    op.add_column(
        "organizations",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    _replace_deletion_scope_constraint("'organization', 'project', 'scan'")
    op.add_column(
        "data_deletion_receipts",
        sa.Column(
            "target_dispositions",
            sa.JSON(),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("data_deletion_receipts", "target_dispositions")
    _replace_deletion_scope_constraint("'project', 'scan'")
    op.drop_column("organizations", "deleted_at")
    op.drop_column("organizations", "lifecycle_status")
