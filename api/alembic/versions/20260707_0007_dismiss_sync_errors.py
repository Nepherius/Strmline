"""Allow sync errors to be dismissed.

Revision ID: 20260707_0007
Revises: 20260706_0006
Create Date: 2026-07-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260707_0007"
down_revision: str | None = "20260706_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "sync_errors",
        sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_sync_errors_dismissed_created_at",
        "sync_errors",
        ["dismissed_at", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_sync_errors_dismissed_created_at", table_name="sync_errors")
    op.drop_column("sync_errors", "dismissed_at")
