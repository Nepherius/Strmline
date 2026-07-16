"""Add persisted series watchlist.

Revision ID: 20260716_0013
Revises: 20260715_0012
Create Date: 2026-07-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260716_0013"
down_revision: str | None = "20260715_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "watchlist_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tmdb_id", sa.Integer(), nullable=False),
        sa.Column("imdb_id", sa.String(length=20), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("year", sa.String(length=20), nullable=True),
        sa.Column("overview", sa.Text(), nullable=False),
        sa.Column("poster_url", sa.Text(), nullable=True),
        sa.Column("media_type", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_watchlist_items")),
        sa.UniqueConstraint("tmdb_id", name="uq_watchlist_items_tmdb_id"),
    )
    op.create_index("ix_watchlist_items_title", "watchlist_items", ["title"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_watchlist_items_title", table_name="watchlist_items")
    op.drop_table("watchlist_items")
