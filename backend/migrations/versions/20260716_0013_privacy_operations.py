"""add privacy operations governance

Revision ID: 20260716_0013
Revises: 20260716_0012
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260716_0013"
down_revision: str | None = "20260716_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


APPEND_ONLY_TABLES = (
    "privacy_processing_records",
    "privacy_processing_record_events",
    "privacy_requests",
    "privacy_request_events",
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
                RAISE EXCEPTION 'privacy governance records are append-only';
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
                    SELECT RAISE(ABORT, 'privacy governance records are append-only');
                END
                """
            )
    else:
        raise RuntimeError(f"append-only privacy triggers are not implemented for {dialect}")


def upgrade() -> None:
    op.create_table(
        "privacy_processing_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("activity_key", sa.String(length=60), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("organization_role", sa.String(length=30), nullable=False),
        sa.Column("purpose_code", sa.String(length=50), nullable=False),
        sa.Column("lawful_basis", sa.String(length=40), nullable=False),
        sa.Column("health_data_processed", sa.Boolean(), nullable=False),
        sa.Column("article9_condition", sa.String(length=50), nullable=False),
        sa.Column("data_subject_categories", sa.JSON(), nullable=False),
        sa.Column("personal_data_categories", sa.JSON(), nullable=False),
        sa.Column("recipient_categories", sa.JSON(), nullable=False),
        sa.Column("processor_references", sa.JSON(), nullable=False),
        sa.Column("processing_locations", sa.JSON(), nullable=False),
        sa.Column("transfer_mechanism", sa.String(length=50), nullable=False),
        sa.Column("transfer_safeguard_reference", sa.String(length=80), nullable=True),
        sa.Column("retention_policy_id", sa.Uuid(), nullable=False),
        sa.Column("retention_policy_version", sa.Integer(), nullable=False),
        sa.Column("security_measure_references", sa.JSON(), nullable=False),
        sa.Column("dpia_required", sa.Boolean(), nullable=False),
        sa.Column("dpia_outcome", sa.String(length=30), nullable=False),
        sa.Column("dpia_reference", sa.String(length=80), nullable=False),
        sa.Column("dpo_review_reference", sa.String(length=80), nullable=False),
        sa.Column("approval_reference", sa.String(length=80), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("version > 0", name="ck_privacy_processing_record_version_positive"),
        sa.CheckConstraint(
            "organization_role IN ('controller', 'processor', 'joint_controller')",
            name="ck_privacy_processing_record_role",
        ),
        sa.CheckConstraint(
            "purpose_code IN ('research_dataset_annotation', 'imaging_quality_assurance', 'ml_dataset_export', "
            "'security_and_audit', 'service_operations', 'customer_support', 'external_ai_inference')",
            name="ck_privacy_processing_record_purpose",
        ),
        sa.CheckConstraint(
            "lawful_basis IN ('consent', 'contract', 'legal_obligation', 'vital_interests', "
            "'public_task', 'legitimate_interests')",
            name="ck_privacy_processing_record_lawful_basis",
        ),
        sa.CheckConstraint(
            "article9_condition IN ('not_applicable', 'explicit_consent', 'employment_social_security', "
            "'vital_interests', 'nonprofit', 'made_public', 'legal_claims', "
            "'substantial_public_interest', 'healthcare', 'public_health', 'research_statistics')",
            name="ck_privacy_processing_record_article9",
        ),
        sa.CheckConstraint(
            "(health_data_processed = false AND article9_condition = 'not_applicable') OR "
            "(health_data_processed = true AND article9_condition <> 'not_applicable')",
            name="ck_privacy_processing_record_health_condition",
        ),
        sa.CheckConstraint(
            "transfer_mechanism IN ('not_applicable', 'adequacy_decision', "
            "'standard_contractual_clauses', 'binding_corporate_rules', 'approved_derogation')",
            name="ck_privacy_processing_record_transfer",
        ),
        sa.CheckConstraint(
            "(transfer_mechanism = 'not_applicable' AND transfer_safeguard_reference IS NULL) OR "
            "(transfer_mechanism <> 'not_applicable' AND transfer_safeguard_reference IS NOT NULL)",
            name="ck_privacy_processing_record_transfer_reference",
        ),
        sa.CheckConstraint(
            "dpia_outcome IN ('not_required', 'approved', 'consultation_required')",
            name="ck_privacy_processing_record_dpia_outcome",
        ),
        sa.CheckConstraint(
            "(dpia_required = false AND dpia_outcome = 'not_required') OR "
            "(dpia_required = true AND dpia_outcome IN ('approved', 'consultation_required'))",
            name="ck_privacy_processing_record_dpia_consistency",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["retention_policy_id"], ["data_retention_policies.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "activity_key", "version", name="uq_privacy_processing_record_version"),
    )
    op.create_index(
        "ix_privacy_processing_records_org_created", "privacy_processing_records", ["organization_id", "created_at"]
    )
    op.create_index(
        "ix_privacy_processing_records_org_activity",
        "privacy_processing_records",
        ["organization_id", "activity_key", "version"],
    )

    op.create_table(
        "privacy_processing_record_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("processing_record_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("action IN ('recorded', 'revoked')", name="ck_privacy_processing_record_event_action"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["processing_record_id"], ["privacy_processing_records.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_privacy_processing_record_events_record_occurred",
        "privacy_processing_record_events",
        ["processing_record_id", "occurred_at"],
    )

    op.create_table(
        "privacy_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("case_reference", sa.String(length=80), nullable=False),
        sa.Column("subject_reference_digest", sa.String(length=64), nullable=False),
        sa.Column("request_type", sa.String(length=30), nullable=False),
        sa.Column("scope_type", sa.String(length=20), nullable=False),
        sa.Column("scope_id", sa.Uuid(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("response_due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "request_type IN ('access', 'rectification', 'restriction', 'objection', 'portability', 'erasure')",
            name="ck_privacy_request_type",
        ),
        sa.CheckConstraint("scope_type IN ('organization', 'project', 'scan')", name="ck_privacy_request_scope"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "case_reference", name="uq_privacy_request_case_reference"),
    )
    op.create_index("ix_privacy_requests_org_created", "privacy_requests", ["organization_id", "created_at"])
    op.create_index("ix_privacy_requests_org_scope", "privacy_requests", ["organization_id", "scope_type", "scope_id"])
    op.create_index("ix_privacy_requests_org_due", "privacy_requests", ["organization_id", "response_due_at"])

    op.create_table(
        "privacy_request_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("privacy_request_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(length=30), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=False),
        sa.Column("reason_code", sa.String(length=50), nullable=True),
        sa.Column("outcome_code", sa.String(length=40), nullable=True),
        sa.Column("evidence_reference", sa.String(length=80), nullable=True),
        sa.Column("linked_deletion_request_id", sa.Uuid(), nullable=True),
        sa.Column("new_due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "action IN ('received', 'identity_verified', 'accepted', 'fulfilled', "
            "'denied', 'cancelled', 'deadline_extended')",
            name="ck_privacy_request_event_action",
        ),
        sa.CheckConstraint(
            "reason_code IS NULL OR reason_code IN ('identity_not_verified', 'request_not_applicable', "
            "'legal_exception', 'insufficient_scope', 'manifestly_unfounded_or_excessive', "
            "'requester_withdrew', 'complexity', 'request_volume')",
            name="ck_privacy_request_event_reason",
        ),
        sa.CheckConstraint(
            "outcome_code IS NULL OR outcome_code IN ('secure_delivery', 'record_corrected', "
            "'processing_restricted', 'objection_applied', 'erasure_verified')",
            name="ck_privacy_request_event_outcome",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["privacy_request_id"], ["privacy_requests.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["linked_deletion_request_id"], ["data_deletion_requests.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_privacy_request_events_request_occurred",
        "privacy_request_events",
        ["privacy_request_id", "occurred_at"],
    )

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

    op.drop_index("ix_privacy_request_events_request_occurred", table_name="privacy_request_events")
    op.drop_table("privacy_request_events")
    op.drop_index("ix_privacy_requests_org_due", table_name="privacy_requests")
    op.drop_index("ix_privacy_requests_org_scope", table_name="privacy_requests")
    op.drop_index("ix_privacy_requests_org_created", table_name="privacy_requests")
    op.drop_table("privacy_requests")
    op.drop_index(
        "ix_privacy_processing_record_events_record_occurred", table_name="privacy_processing_record_events"
    )
    op.drop_table("privacy_processing_record_events")
    op.drop_index("ix_privacy_processing_records_org_activity", table_name="privacy_processing_records")
    op.drop_index("ix_privacy_processing_records_org_created", table_name="privacy_processing_records")
    op.drop_table("privacy_processing_records")
