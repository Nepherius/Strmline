"""Add stream selections.

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-05 00:00:00.000000+00:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "stream_selections",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("stream_key", sa.String(length=64), nullable=False),
        sa.Column("media_type", sa.String(length=20), nullable=False),
        sa.Column("media_id", sa.String(length=100), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("source_name", sa.Text(), nullable=True),
        sa.Column("info_hash", sa.String(length=100), nullable=True),
        sa.Column("torbox_torrent_id", sa.String(length=100), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_stream_selections")),
        sa.UniqueConstraint("stream_key", name="uq_stream_selections_stream_key"),
    )
    op.create_index(
        "ix_stream_selections_info_hash",
        "stream_selections",
        ["info_hash"],
        unique=False,
    )
    op.create_index(
        "ix_stream_selections_status",
        "stream_selections",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_stream_selections_status", table_name="stream_selections")
    op.drop_index("ix_stream_selections_info_hash", table_name="stream_selections")
    op.drop_table("stream_selections")
