"""add external AI governance

Revision ID: 20260716_0012
Revises: 20260716_0011
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260716_0012"
down_revision: str | None = "20260716_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


APPEND_ONLY_TABLES = (
    "external_ai_provider_approvals",
    "external_ai_provider_events",
    "external_ai_data_flow_approvals",
    "external_ai_data_flow_events",
    "external_ai_egress_decisions",
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
                RAISE EXCEPTION 'external AI governance records are append-only';
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
                    SELECT RAISE(ABORT, 'external AI governance records are append-only');
                END
                """
            )
    else:
        raise RuntimeError(f"append-only external AI triggers are not implemented for {dialect}")


def upgrade() -> None:
    op.create_table(
        "external_ai_provider_approvals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("provider_key", sa.String(length=60), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("model_name", sa.String(length=120), nullable=False),
        sa.Column("model_version", sa.String(length=80), nullable=False),
        sa.Column("purpose_code", sa.String(length=40), nullable=False),
        sa.Column("endpoint_origin", sa.String(length=255), nullable=False),
        sa.Column("region_code", sa.String(length=40), nullable=False),
        sa.Column("data_classes", sa.JSON(), nullable=False),
        sa.Column("retention_days", sa.Integer(), nullable=False),
        sa.Column("training_use_allowed", sa.Boolean(), nullable=False),
        sa.Column("subprocessors", sa.JSON(), nullable=False),
        sa.Column("transfer_mechanism", sa.String(length=40), nullable=False),
        sa.Column("contract_owner_reference", sa.String(length=80), nullable=False),
        sa.Column("approval_reference", sa.String(length=80), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("version > 0", name="ck_external_ai_provider_version_positive"),
        sa.CheckConstraint(
            "purpose_code IN ('research_inference', 'annotation_assistance', 'quality_assurance')",
            name="ck_external_ai_provider_purpose",
        ),
        sa.CheckConstraint(
            "transfer_mechanism IN ('not_applicable', 'adequacy_decision', 'standard_contractual_clauses', 'approved_derogation')",
            name="ck_external_ai_provider_transfer",
        ),
        sa.CheckConstraint("retention_days >= 0", name="ck_external_ai_provider_retention"),
        sa.CheckConstraint("training_use_allowed = false", name="ck_external_ai_provider_no_training"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "provider_key", "version", name="uq_external_ai_provider_version"),
    )
    op.create_index(
        "ix_external_ai_providers_org_created", "external_ai_provider_approvals", ["organization_id", "created_at"]
    )

    op.create_table(
        "external_ai_provider_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("provider_approval_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("action IN ('approved', 'revoked')", name="ck_external_ai_provider_event_action"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["provider_approval_id"], ["external_ai_provider_approvals.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_external_ai_provider_events_provider_occurred",
        "external_ai_provider_events",
        ["provider_approval_id", "occurred_at"],
    )

    op.create_table(
        "external_ai_data_flow_approvals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("provider_approval_id", sa.Uuid(), nullable=False),
        sa.Column("purpose_code", sa.String(length=40), nullable=False),
        sa.Column("data_classes", sa.JSON(), nullable=False),
        sa.Column("approval_reference", sa.String(length=80), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "purpose_code IN ('research_inference', 'annotation_assistance', 'quality_assurance')",
            name="ck_external_ai_flow_purpose",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["provider_approval_id"], ["external_ai_provider_approvals.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_external_ai_flows_org_project",
        "external_ai_data_flow_approvals",
        ["organization_id", "project_id", "created_at"],
    )

    op.create_table(
        "external_ai_data_flow_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("data_flow_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("action IN ('approved', 'revoked')", name="ck_external_ai_flow_event_action"),
        sa.ForeignKeyConstraint(["data_flow_id"], ["external_ai_data_flow_approvals.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_external_ai_flow_events_flow_occurred",
        "external_ai_data_flow_events",
        ["data_flow_id", "occurred_at"],
    )

    op.create_table(
        "external_ai_egress_decisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("provider_approval_id", sa.Uuid(), nullable=False),
        sa.Column("data_flow_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=False),
        sa.Column("purpose_code", sa.String(length=40), nullable=False),
        sa.Column("requested_data_classes", sa.JSON(), nullable=False),
        sa.Column("result", sa.String(length=20), nullable=False),
        sa.Column("reason_code", sa.String(length=40), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("result IN ('allowed', 'denied')", name="ck_external_ai_decision_result"),
        sa.CheckConstraint(
            "reason_code IN ('authorized', 'feature_disabled', 'provider_revoked', 'provider_unapproved', "
            "'flow_revoked', 'flow_unapproved', 'flow_expired', 'origin_not_allowlisted', "
            "'project_unavailable', 'purpose_not_approved', "
            "'data_class_not_approved', 'dataset_not_deidentified')",
            name="ck_external_ai_decision_reason",
        ),
        sa.ForeignKeyConstraint(["data_flow_id"], ["external_ai_data_flow_approvals.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["provider_approval_id"], ["external_ai_provider_approvals.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_external_ai_decisions_org_occurred",
        "external_ai_egress_decisions",
        ["organization_id", "occurred_at"],
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

    op.drop_index("ix_external_ai_decisions_org_occurred", table_name="external_ai_egress_decisions")
    op.drop_table("external_ai_egress_decisions")
    op.drop_index("ix_external_ai_flow_events_flow_occurred", table_name="external_ai_data_flow_events")
    op.drop_table("external_ai_data_flow_events")
    op.drop_index("ix_external_ai_flows_org_project", table_name="external_ai_data_flow_approvals")
    op.drop_table("external_ai_data_flow_approvals")
    op.drop_index("ix_external_ai_provider_events_provider_occurred", table_name="external_ai_provider_events")
    op.drop_table("external_ai_provider_events")
    op.drop_index("ix_external_ai_providers_org_created", table_name="external_ai_provider_approvals")
    op.drop_table("external_ai_provider_approvals")
