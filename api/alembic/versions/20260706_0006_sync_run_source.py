"""Add sync run source.

Revision ID: 20260706_0006
Revises: 20260706_0005
Create Date: 2026-07-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260706_0006"
down_revision: str | None = "20260706_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "sync_runs",
        sa.Column(
            "source",
            sa.String(length=30),
            nullable=False,
            server_default="manual",
        ),
    )
    op.create_index(
        "ix_sync_runs_source_started_at",
        "sync_runs",
        ["source", "started_at"],
    )
    op.alter_column("sync_runs", "source", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_sync_runs_source_started_at", table_name="sync_runs")
    op.drop_column("sync_runs", "source")
