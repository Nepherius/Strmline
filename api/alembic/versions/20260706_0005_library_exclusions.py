"""Add library exclusions.

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-06 00:00:00.000000+00:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "library_exclusions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("category", sa.String(length=20), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("relative_prefix", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_library_exclusions")),
        sa.UniqueConstraint(
            "relative_prefix",
            name="uq_library_exclusions_relative_prefix",
        ),
    )
    op.create_index(
        "ix_library_exclusions_category",
        "library_exclusions",
        ["category"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_library_exclusions_category", table_name="library_exclusions")
    op.drop_table("library_exclusions")
