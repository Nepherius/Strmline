"""Add manual classification overrides.

Revision ID: 20260707_0008
Revises: 20260707_0007
Create Date: 2026-07-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260707_0008"
down_revision: str | None = "20260707_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "classification_overrides",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source_category", sa.String(length=20), nullable=False),
        sa.Column("source_prefix", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("target_category", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_classification_overrides")),
        sa.UniqueConstraint(
            "source_prefix",
            name="uq_classification_overrides_source_prefix",
        ),
    )
    op.create_index(
        "ix_classification_overrides_target_category",
        "classification_overrides",
        ["target_category"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_classification_overrides_target_category", table_name="classification_overrides"
    )
    op.drop_table("classification_overrides")
