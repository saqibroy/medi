"""add immutable dataset releases

Revision ID: 20260716_0010
Revises: 20260716_0009
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260716_0010"
down_revision: str | None = "20260716_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _create_append_only_triggers(table_name: str) -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        function_name = f"reject_{table_name}_mutation"
        op.execute(
            f"""
            CREATE FUNCTION {function_name}()
            RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'dataset releases are append-only';
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
                    SELECT RAISE(ABORT, 'dataset releases are append-only');
                END
                """
            )
    else:
        raise RuntimeError(f"append-only release triggers are not implemented for {dialect}")


def upgrade() -> None:
    op.create_table(
        "dataset_releases",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("schema_version", sa.String(length=80), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("manifest_sha256", sa.String(length=64), nullable=False),
        sa.Column("manifest", sa.JSON(), nullable=False),
        sa.Column("supersedes_release_id", sa.Uuid(), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("version > 0", name="ck_dataset_release_version_positive"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["supersedes_release_id"], ["dataset_releases.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "version", name="uq_dataset_releases_project_version"),
    )
    op.create_index("ix_dataset_releases_org_created", "dataset_releases", ["organization_id", "created_at"])
    op.create_index("ix_dataset_releases_project_version", "dataset_releases", ["project_id", "version"])

    op.create_table(
        "dataset_release_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("release_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(length=30), nullable=False),
        sa.Column("reason_code", sa.String(length=40), nullable=True),
        sa.Column("related_release_id", sa.Uuid(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("action IN ('created', 'superseded', 'revoked')", name="ck_dataset_release_event_action"),
        sa.CheckConstraint(
            "reason_code IS NULL OR reason_code IN ('quality_issue', 'source_withdrawn', 'policy_change', 'superseded', 'other')",
            name="ck_dataset_release_event_reason",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["related_release_id"], ["dataset_releases.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["release_id"], ["dataset_releases.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_dataset_release_events_release_occurred", "dataset_release_events", ["release_id", "occurred_at"])
    op.create_index("ix_dataset_release_events_org_occurred", "dataset_release_events", ["organization_id", "occurred_at"])
    _create_append_only_triggers("dataset_releases")
    _create_append_only_triggers("dataset_release_events")


def downgrade() -> None:
    dialect = op.get_bind().dialect.name
    for table_name in ("dataset_release_events", "dataset_releases"):
        if dialect == "postgresql":
            op.execute(f"DROP TRIGGER IF EXISTS {table_name}_append_only ON {table_name}")
            op.execute(f"DROP FUNCTION IF EXISTS reject_{table_name}_mutation()")
        elif dialect == "sqlite":
            op.execute(f"DROP TRIGGER IF EXISTS {table_name}_no_delete")
            op.execute(f"DROP TRIGGER IF EXISTS {table_name}_no_update")

    op.drop_index("ix_dataset_release_events_org_occurred", table_name="dataset_release_events")
    op.drop_index("ix_dataset_release_events_release_occurred", table_name="dataset_release_events")
    op.drop_table("dataset_release_events")
    op.drop_index("ix_dataset_releases_project_version", table_name="dataset_releases")
    op.drop_index("ix_dataset_releases_org_created", table_name="dataset_releases")
    op.drop_table("dataset_releases")
