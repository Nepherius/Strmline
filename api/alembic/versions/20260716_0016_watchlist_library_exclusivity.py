"""Remove watchlist entries already present in the library.

Revision ID: 20260716_0016
Revises: 20260716_0015
Create Date: 2026-07-16
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260716_0016"
down_revision: str | None = "20260716_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        DELETE FROM watchlist_items AS watchlist
        USING media_items AS media, library_entries AS entry, generated_files AS generated
        WHERE media.id = entry.media_item_id
          AND entry.id = generated.library_entry_id
          AND media.tmdb_id = CAST(watchlist.tmdb_id AS TEXT)
          AND (
            (watchlist.media_type = 'movie' AND entry.category = 'movies')
            OR
            (watchlist.media_type = 'series' AND entry.category IN ('shows', 'anime'))
          )
          AND NOT EXISTS (
            SELECT 1
            FROM library_exclusions AS exclusion
            WHERE generated.relative_path = exclusion.relative_prefix
               OR generated.relative_path LIKE exclusion.relative_prefix || '/%'
          )
        """
    )


def downgrade() -> None:
    pass
