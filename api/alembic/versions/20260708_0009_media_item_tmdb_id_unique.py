"""Add unique index on media_items tmdb_id.

Revision ID: 20260708_0009
Revises: 20260707_0008
Create Date: 2026-07-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260708_0009"
down_revision: str | None = "20260707_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_media_items_tmdb_id",
        "media_items",
        ["tmdb_id"],
        unique=True,
        postgresql_where=sa.text("tmdb_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_media_items_tmdb_id",
        table_name="media_items",
    )
