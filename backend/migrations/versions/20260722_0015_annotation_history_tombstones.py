"""add immutable annotation history tombstones

Revision ID: 20260722_0015
Revises: 20260722_0014
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260722_0015"
down_revision: str | None = "20260722_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _create_append_only_triggers() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.execute(
            """
            CREATE FUNCTION reject_annotation_history_tombstone_mutation()
            RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'annotation history tombstones are append-only';
            END;
            $$ LANGUAGE plpgsql
            """
        )
        op.execute(
            """
            CREATE TRIGGER annotation_history_tombstones_append_only
            BEFORE UPDATE OR DELETE ON annotation_history_tombstones
            FOR EACH ROW EXECUTE FUNCTION reject_annotation_history_tombstone_mutation()
            """
        )
    elif dialect == "sqlite":
        for operation in ("UPDATE", "DELETE"):
            op.execute(
                f"""
                CREATE TRIGGER annotation_history_tombstones_no_{operation.lower()}
                BEFORE {operation} ON annotation_history_tombstones
                BEGIN
                    SELECT RAISE(ABORT, 'annotation history tombstones are append-only');
                END
                """
            )
    else:
        raise RuntimeError(f"append-only annotation history triggers are not implemented for {dialect}")


def upgrade() -> None:
    op.create_table(
        "annotation_history_tombstones",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("scan_id", sa.Uuid(), nullable=False),
        sa.Column("annotation_id", sa.Uuid(), nullable=False),
        sa.Column("deleted_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("deletion_source", sa.String(length=30), nullable=False),
        sa.Column("history_entry_count", sa.Integer(), nullable=False),
        sa.Column("action_counts", sa.JSON(), nullable=False),
        sa.Column("changed_fields", sa.JSON(), nullable=False),
        sa.Column("first_history_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_history_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("history_lineage_hash", sa.String(length=64), nullable=False),
        sa.Column("integrity_hash", sa.String(length=64), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("history_entry_count >= 0", name="ck_annotation_history_tombstone_count"),
        sa.CheckConstraint(
            "deletion_source IN ('annotation_api', 'data_lifecycle')",
            name="ck_annotation_history_tombstone_source",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("annotation_id", name="uq_annotation_history_tombstone_annotation"),
    )
    op.create_index(
        "ix_annotation_history_tombstones_org_deleted",
        "annotation_history_tombstones",
        ["organization_id", "deleted_at"],
    )
    op.create_index("ix_annotation_history_tombstones_project", "annotation_history_tombstones", ["project_id"])
    op.create_index("ix_annotation_history_tombstones_scan", "annotation_history_tombstones", ["scan_id"])
    _create_append_only_triggers()


def downgrade() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS annotation_history_tombstones_append_only ON annotation_history_tombstones")
        op.execute("DROP FUNCTION IF EXISTS reject_annotation_history_tombstone_mutation()")
    elif dialect == "sqlite":
        op.execute("DROP TRIGGER IF EXISTS annotation_history_tombstones_no_delete")
        op.execute("DROP TRIGGER IF EXISTS annotation_history_tombstones_no_update")

    op.drop_index("ix_annotation_history_tombstones_scan", table_name="annotation_history_tombstones")
    op.drop_index("ix_annotation_history_tombstones_project", table_name="annotation_history_tombstones")
    op.drop_index("ix_annotation_history_tombstones_org_deleted", table_name="annotation_history_tombstones")
    op.drop_table("annotation_history_tombstones")
