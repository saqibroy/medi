"""add retained private dataset release artifacts

Revision ID: 20260723_0016
Revises: 20260722_0015
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260723_0016"
down_revision: str | None = "20260722_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _create_append_only_triggers() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.execute(
            """
            CREATE FUNCTION reject_dataset_release_artifact_mutation()
            RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'dataset release artifacts are append-only';
            END;
            $$ LANGUAGE plpgsql
            """
        )
        op.execute(
            """
            CREATE TRIGGER dataset_release_artifacts_append_only
            BEFORE UPDATE OR DELETE ON dataset_release_artifacts
            FOR EACH ROW EXECUTE FUNCTION reject_dataset_release_artifact_mutation()
            """
        )
    elif dialect == "sqlite":
        for operation in ("UPDATE", "DELETE"):
            op.execute(
                f"""
                CREATE TRIGGER dataset_release_artifacts_no_{operation.lower()}
                BEFORE {operation} ON dataset_release_artifacts
                BEGIN
                    SELECT RAISE(ABORT, 'dataset release artifacts are append-only');
                END
                """
            )
    else:
        raise RuntimeError(f"append-only release artifact triggers are not implemented for {dialect}")


def upgrade() -> None:
    op.create_table(
        "dataset_release_artifacts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("release_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("artifact_type", sa.String(length=40), nullable=False),
        sa.Column("schema_version", sa.String(length=80), nullable=False),
        sa.Column("media_type", sa.String(length=100), nullable=False),
        sa.Column("storage_key", sa.String(length=700), nullable=False),
        sa.Column("object_version_id", sa.String(length=1024), nullable=False),
        sa.Column("checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("artifact_type = 'portable_manifest'", name="ck_dataset_release_artifact_type"),
        sa.CheckConstraint("byte_size > 0", name="ck_dataset_release_artifact_byte_size"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["release_id"], ["dataset_releases.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("release_id", "artifact_type", name="uq_dataset_release_artifact_type"),
        sa.UniqueConstraint("storage_key"),
    )
    op.create_index(
        "ix_dataset_release_artifacts_org_created",
        "dataset_release_artifacts",
        ["organization_id", "created_at"],
    )
    op.create_index("ix_dataset_release_artifacts_project", "dataset_release_artifacts", ["project_id"])
    _create_append_only_triggers()


def downgrade() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS dataset_release_artifacts_append_only ON dataset_release_artifacts")
        op.execute("DROP FUNCTION IF EXISTS reject_dataset_release_artifact_mutation()")
    elif dialect == "sqlite":
        op.execute("DROP TRIGGER IF EXISTS dataset_release_artifacts_no_delete")
        op.execute("DROP TRIGGER IF EXISTS dataset_release_artifacts_no_update")

    op.drop_index("ix_dataset_release_artifacts_project", table_name="dataset_release_artifacts")
    op.drop_index("ix_dataset_release_artifacts_org_created", table_name="dataset_release_artifacts")
    op.drop_table("dataset_release_artifacts")
