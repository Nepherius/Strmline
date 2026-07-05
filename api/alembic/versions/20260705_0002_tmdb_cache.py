"""Add TMDB cache entries.

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-05 00:00:00.000000+00:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tmdb_cache_entries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("cache_key", sa.String(length=255), nullable=False),
        sa.Column("endpoint", sa.Text(), nullable=False),
        sa.Column("request_params", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("response_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tmdb_cache_entries")),
        sa.UniqueConstraint("cache_key", name="uq_tmdb_cache_entries_cache_key"),
    )
    op.create_index(
        "ix_tmdb_cache_entries_expires_at",
        "tmdb_cache_entries",
        ["expires_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_tmdb_cache_entries_expires_at", table_name="tmdb_cache_entries")
    op.drop_table("tmdb_cache_entries")
