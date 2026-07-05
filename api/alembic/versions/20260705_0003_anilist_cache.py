"""Add AniList cache entries.

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-05 00:00:00.000000+00:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "anilist_cache_entries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("cache_key", sa.String(length=255), nullable=False),
        sa.Column("operation_name", sa.String(length=100), nullable=False),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("variables", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("response_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_anilist_cache_entries")),
        sa.UniqueConstraint("cache_key", name="uq_anilist_cache_entries_cache_key"),
    )
    op.create_index(
        "ix_anilist_cache_entries_expires_at",
        "anilist_cache_entries",
        ["expires_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_anilist_cache_entries_expires_at", table_name="anilist_cache_entries")
    op.drop_table("anilist_cache_entries")
