"""Add the generated-file processing fingerprint.

Revision ID: 20260728_0023
Revises: 20260721_0022
Create Date: 2026-07-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260728_0023"
down_revision: str | None = "20260721_0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "generated_files",
        sa.Column("processing_fingerprint", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("generated_files", "processing_fingerprint")
