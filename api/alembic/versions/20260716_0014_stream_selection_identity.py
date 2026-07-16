"""Persist canonical media identity on stream selections.

Revision ID: 20260716_0014
Revises: 20260716_0013
Create Date: 2026-07-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260716_0014"
down_revision: str | None = "20260716_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("stream_selections", sa.Column("tmdb_id", sa.String(40), nullable=True))
    op.add_column("stream_selections", sa.Column("media_title", sa.Text(), nullable=True))
    op.add_column("stream_selections", sa.Column("media_year", sa.Integer(), nullable=True))
    op.add_column("stream_selections", sa.Column("media_poster_path", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("stream_selections", "media_poster_path")
    op.drop_column("stream_selections", "media_year")
    op.drop_column("stream_selections", "media_title")
    op.drop_column("stream_selections", "tmdb_id")
