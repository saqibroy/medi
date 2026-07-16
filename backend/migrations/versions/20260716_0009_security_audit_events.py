"""add append-only security audit events

Revision ID: 20260716_0009
Revises: 20260716_0008
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260716_0009"
down_revision: str | None = "20260716_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "security_audit_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=True),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("actor_session_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("result", sa.String(length=20), nullable=False),
        sa.Column("target_type", sa.String(length=60), nullable=True),
        sa.Column("target_id", sa.Uuid(), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("integrity_hash", sa.String(length=64), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("result IN ('succeeded', 'failed', 'denied', 'error')", name="ck_security_audit_event_result"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_security_audit_events_org_occurred", "security_audit_events", ["organization_id", "occurred_at"])
    op.create_index("ix_security_audit_events_action_occurred", "security_audit_events", ["action", "occurred_at"])

    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.execute(
            """
            CREATE FUNCTION reject_security_audit_event_mutation()
            RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'security audit events are append-only';
            END;
            $$ LANGUAGE plpgsql
            """
        )
        op.execute(
            """
            CREATE TRIGGER security_audit_events_append_only
            BEFORE UPDATE OR DELETE ON security_audit_events
            FOR EACH ROW EXECUTE FUNCTION reject_security_audit_event_mutation()
            """
        )
    elif dialect == "sqlite":
        op.execute(
            """
            CREATE TRIGGER security_audit_events_no_update
            BEFORE UPDATE ON security_audit_events
            BEGIN
                SELECT RAISE(ABORT, 'security audit events are append-only');
            END
            """
        )
        op.execute(
            """
            CREATE TRIGGER security_audit_events_no_delete
            BEFORE DELETE ON security_audit_events
            BEGIN
                SELECT RAISE(ABORT, 'security audit events are append-only');
            END
            """
        )
    else:
        raise RuntimeError(f"append-only audit triggers are not implemented for {dialect}")


def downgrade() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS security_audit_events_append_only ON security_audit_events")
        op.execute("DROP FUNCTION IF EXISTS reject_security_audit_event_mutation()")
    elif dialect == "sqlite":
        op.execute("DROP TRIGGER IF EXISTS security_audit_events_no_delete")
        op.execute("DROP TRIGGER IF EXISTS security_audit_events_no_update")

    op.drop_index("ix_security_audit_events_action_occurred", table_name="security_audit_events")
    op.drop_index("ix_security_audit_events_org_occurred", table_name="security_audit_events")
    op.drop_table("security_audit_events")
