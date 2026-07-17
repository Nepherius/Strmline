"""Persist manual TMDB identity precedence across synchronization.

Revision ID: 20260717_0018
Revises: 20260716_0017
Create Date: 2026-07-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260717_0018"
down_revision: str | None = "20260716_0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "media_items",
        sa.Column(
            "tmdb_id_locked",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("media_items", "tmdb_id_locked")
