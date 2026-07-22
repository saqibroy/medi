"""add session idle activity tracking

Revision ID: 20260722_0014
Revises: 20260716_0013
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260722_0014"
down_revision: str | None = "20260716_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "user_sessions",
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_user_sessions_last_seen_at", "user_sessions", ["last_seen_at"])


def downgrade() -> None:
    op.drop_index("ix_user_sessions_last_seen_at", table_name="user_sessions")
    op.drop_column("user_sessions", "last_seen_at")
