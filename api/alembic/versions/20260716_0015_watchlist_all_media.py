"""Allow movie and series watchlist identities.

Revision ID: 20260716_0015
Revises: 20260716_0014
Create Date: 2026-07-16
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260716_0015"
down_revision: str | None = "20260716_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("uq_watchlist_items_tmdb_id", "watchlist_items", type_="unique")
    op.create_unique_constraint(
        "uq_watchlist_items_media_type_tmdb_id",
        "watchlist_items",
        ["media_type", "tmdb_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_watchlist_items_media_type_tmdb_id",
        "watchlist_items",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_watchlist_items_tmdb_id",
        "watchlist_items",
        ["tmdb_id"],
    )
