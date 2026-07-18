"""Persist TorBox availability health for library entries.

Revision ID: 20260718_0021
Revises: 20260718_0020
Create Date: 2026-07-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260718_0021"
down_revision: str | None = "20260718_0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    _ = op.create_table(
        "library_entry_health",
        sa.Column("library_entry_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("info_hash", sa.String(100), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('ready', 'recoverable', 'unavailable', 'unknown')",
            name="ck_library_entry_health_status",
        ),
        sa.ForeignKeyConstraint(
            ["library_entry_id"],
            ["library_entries.id"],
            name=op.f("fk_library_entry_health_library_entry_id_library_entries"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "library_entry_id",
            name=op.f("pk_library_entry_health"),
        ),
    )
    op.create_index(
        "ix_library_entry_health_status",
        "library_entry_health",
        ["status"],
    )
    op.create_index(
        "ix_library_entry_health_checked_at",
        "library_entry_health",
        ["checked_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_library_entry_health_checked_at", table_name="library_entry_health")
    op.drop_index("ix_library_entry_health_status", table_name="library_entry_health")
    op.drop_table("library_entry_health")
