"""Add indexes for paginated library browsing and substring search.

Revision ID: 20260718_0020
Revises: 20260718_0019
Create Date: 2026-07-18
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260718_0020"
down_revision: str | None = "20260718_0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.create_index(
        "ix_library_entries_media_category",
        "library_entries",
        ["media_item_id", "category"],
    )
    op.execute("CREATE INDEX ix_media_items_title_lower ON media_items (lower(title), id)")
    op.execute(
        "CREATE INDEX ix_media_items_title_trgm ON media_items USING gin (lower(title) gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX ix_generated_files_path_trgm ON generated_files USING gin (lower(relative_path) gin_trgm_ops)"
    )


def downgrade() -> None:
    op.drop_index("ix_generated_files_path_trgm", table_name="generated_files")
    op.drop_index("ix_media_items_title_trgm", table_name="media_items")
    op.drop_index("ix_media_items_title_lower", table_name="media_items")
    op.drop_index(
        "ix_library_entries_media_category",
        table_name="library_entries",
    )
