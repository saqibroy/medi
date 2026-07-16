"""add data lifecycle governance

Revision ID: 20260716_0011
Revises: 20260716_0010
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260716_0011"
down_revision: str | None = "20260716_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


APPEND_ONLY_TABLES = (
    "data_retention_policies",
    "legal_holds",
    "legal_hold_events",
    "data_deletion_requests",
    "data_deletion_events",
    "data_deletion_receipts",
)


def _create_append_only_triggers(table_name: str) -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        function_name = f"reject_{table_name}_mutation"
        op.execute(
            f"""
            CREATE FUNCTION {function_name}()
            RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'data governance records are append-only';
            END;
            $$ LANGUAGE plpgsql
            """
        )
        op.execute(
            f"""
            CREATE TRIGGER {table_name}_append_only
            BEFORE UPDATE OR DELETE ON {table_name}
            FOR EACH ROW EXECUTE FUNCTION {function_name}()
            """
        )
    elif dialect == "sqlite":
        for operation in ("UPDATE", "DELETE"):
            op.execute(
                f"""
                CREATE TRIGGER {table_name}_no_{operation.lower()}
                BEFORE {operation} ON {table_name}
                BEGIN
                    SELECT RAISE(ABORT, 'data governance records are append-only');
                END
                """
            )
    else:
        raise RuntimeError(f"append-only governance triggers are not implemented for {dialect}")


def upgrade() -> None:
    op.add_column("projects", sa.Column("lifecycle_status", sa.String(length=30), server_default="active", nullable=False))
    op.add_column("projects", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "data_retention_policies",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("approval_reference", sa.String(length=80), nullable=False),
        sa.Column("original_minimum_days", sa.Integer(), nullable=False),
        sa.Column("mask_minimum_days", sa.Integer(), nullable=False),
        sa.Column("metadata_minimum_days", sa.Integer(), nullable=False),
        sa.Column("dataset_release_minimum_days", sa.Integer(), nullable=False),
        sa.Column("audit_minimum_days", sa.Integer(), nullable=False),
        sa.Column("backup_retention_days", sa.Integer(), nullable=False),
        sa.Column("rpo_hours", sa.Integer(), nullable=False),
        sa.Column("rto_hours", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("version > 0", name="ck_data_retention_policy_version_positive"),
        sa.CheckConstraint("original_minimum_days >= 0", name="ck_retention_original_days"),
        sa.CheckConstraint("mask_minimum_days >= 0", name="ck_retention_mask_days"),
        sa.CheckConstraint("metadata_minimum_days >= 0", name="ck_retention_metadata_days"),
        sa.CheckConstraint("dataset_release_minimum_days >= 0", name="ck_retention_release_days"),
        sa.CheckConstraint("audit_minimum_days >= 0", name="ck_retention_audit_days"),
        sa.CheckConstraint("backup_retention_days > 0", name="ck_retention_backup_days"),
        sa.CheckConstraint("rpo_hours > 0", name="ck_retention_rpo_hours"),
        sa.CheckConstraint("rto_hours > 0", name="ck_retention_rto_hours"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "version", name="uq_data_retention_policy_org_version"),
    )
    op.create_index("ix_data_retention_policies_org_created", "data_retention_policies", ["organization_id", "created_at"])

    op.create_table(
        "legal_holds",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("scope_type", sa.String(length=30), nullable=False),
        sa.Column("scope_id", sa.Uuid(), nullable=False),
        sa.Column("reason_code", sa.String(length=40), nullable=False),
        sa.Column("approval_reference", sa.String(length=80), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("scope_type IN ('organization', 'project', 'scan')", name="ck_legal_hold_scope"),
        sa.CheckConstraint(
            "reason_code IN ('litigation', 'regulatory', 'security_incident', 'customer_request')",
            name="ck_legal_hold_reason",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_legal_holds_org_scope", "legal_holds", ["organization_id", "scope_type", "scope_id"])

    op.create_table(
        "legal_hold_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("hold_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("action IN ('applied', 'released')", name="ck_legal_hold_event_action"),
        sa.ForeignKeyConstraint(["hold_id"], ["legal_holds.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_legal_hold_events_hold_occurred", "legal_hold_events", ["hold_id", "occurred_at"])

    op.create_table(
        "data_deletion_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("scope_type", sa.String(length=20), nullable=False),
        sa.Column("scope_id", sa.Uuid(), nullable=False),
        sa.Column("reason_code", sa.String(length=40), nullable=False),
        sa.Column("approval_reference", sa.String(length=80), nullable=False),
        sa.Column("retention_policy_id", sa.Uuid(), nullable=False),
        sa.Column("retention_policy_version", sa.Integer(), nullable=False),
        sa.Column("inventory", sa.JSON(), nullable=False),
        sa.Column("earliest_execute_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("requested_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("scope_type IN ('project', 'scan')", name="ck_data_deletion_request_scope"),
        sa.CheckConstraint(
            "reason_code IN ('erasure_request', 'source_withdrawal', 'contract_end', 'duplicate_data')",
            name="ck_data_deletion_request_reason",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["retention_policy_id"], ["data_retention_policies.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_data_deletion_requests_org_created", "data_deletion_requests", ["organization_id", "created_at"])
    op.create_index("ix_data_deletion_requests_org_scope", "data_deletion_requests", ["organization_id", "scope_type", "scope_id"])

    op.create_table(
        "data_deletion_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "action IN ('requested', 'approved', 'cancelled', 'executed', 'verified', 'failed')",
            name="ck_data_deletion_event_action",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["request_id"], ["data_deletion_requests.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_data_deletion_events_request_occurred", "data_deletion_events", ["request_id", "occurred_at"])

    op.create_table(
        "data_deletion_receipts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("scope_type", sa.String(length=20), nullable=False),
        sa.Column("scope_id", sa.Uuid(), nullable=False),
        sa.Column("deleted_counts", sa.JSON(), nullable=False),
        sa.Column("object_versions_deleted", sa.Integer(), nullable=False),
        sa.Column("delete_markers_deleted", sa.Integer(), nullable=False),
        sa.Column("revoked_releases", sa.Integer(), nullable=False),
        sa.Column("backup_disposition", sa.String(length=30), nullable=False),
        sa.Column("backup_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("operator_user_id", sa.Uuid(), nullable=False),
        sa.Column("receipt_sha256", sa.String(length=64), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "backup_disposition IN ('expires_per_policy', 'not_applicable')",
            name="ck_data_deletion_receipt_backup_disposition",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["request_id"], ["data_deletion_requests.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("request_id"),
    )
    op.create_index("ix_data_deletion_receipts_org_completed", "data_deletion_receipts", ["organization_id", "completed_at"])

    for table_name in APPEND_ONLY_TABLES:
        _create_append_only_triggers(table_name)


def downgrade() -> None:
    dialect = op.get_bind().dialect.name
    for table_name in reversed(APPEND_ONLY_TABLES):
        if dialect == "postgresql":
            op.execute(f"DROP TRIGGER IF EXISTS {table_name}_append_only ON {table_name}")
            op.execute(f"DROP FUNCTION IF EXISTS reject_{table_name}_mutation()")
        elif dialect == "sqlite":
            op.execute(f"DROP TRIGGER IF EXISTS {table_name}_no_delete")
            op.execute(f"DROP TRIGGER IF EXISTS {table_name}_no_update")

    op.drop_index("ix_data_deletion_receipts_org_completed", table_name="data_deletion_receipts")
    op.drop_table("data_deletion_receipts")
    op.drop_index("ix_data_deletion_events_request_occurred", table_name="data_deletion_events")
    op.drop_table("data_deletion_events")
    op.drop_index("ix_data_deletion_requests_org_scope", table_name="data_deletion_requests")
    op.drop_index("ix_data_deletion_requests_org_created", table_name="data_deletion_requests")
    op.drop_table("data_deletion_requests")
    op.drop_index("ix_legal_hold_events_hold_occurred", table_name="legal_hold_events")
    op.drop_table("legal_hold_events")
    op.drop_index("ix_legal_holds_org_scope", table_name="legal_holds")
    op.drop_table("legal_holds")
    op.drop_index("ix_data_retention_policies_org_created", table_name="data_retention_policies")
    op.drop_table("data_retention_policies")
    op.drop_column("projects", "deleted_at")
    op.drop_column("projects", "lifecycle_status")
