"""Add durable source identity for permanent virtual library entries.

Revision ID: 20260715_0012
Revises: 20260714_0011
Create Date: 2026-07-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260715_0012"
down_revision: str | None = "20260714_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("library_entries", sa.Column("info_hash", sa.String(100), nullable=True))
    op.add_column("library_entries", sa.Column("source_kind", sa.String(20), nullable=True))
    op.add_column("library_entries", sa.Column("source_item_id", sa.String(100), nullable=True))
    op.add_column("library_entries", sa.Column("source_item_name", sa.Text(), nullable=True))
    op.add_column("library_entries", sa.Column("source_file_id", sa.String(100), nullable=True))
    op.add_column("library_entries", sa.Column("source_file_name", sa.Text(), nullable=True))
    op.add_column("library_entries", sa.Column("source_file_path", sa.Text(), nullable=True))
    op.add_column(
        "library_entries",
        sa.Column("source_file_mime_type", sa.String(255), nullable=True),
    )
    op.add_column("library_entries", sa.Column("source_file_size", sa.BigInteger(), nullable=True))
    op.create_index("ix_library_entries_info_hash", "library_entries", ["info_hash"])

    op.execute(
        sa.text(
            """
            UPDATE library_entries AS library
            SET source_kind = item.kind,
                source_item_id = item.external_id,
                source_item_name = item.name,
                source_file_id = file.external_id,
                source_file_name = file.file_name,
                source_file_path = file.path,
                source_file_mime_type = file.mime_type,
                source_file_size = file.size
            FROM torbox_files AS file
            JOIN torbox_items AS item ON item.id = file.torbox_item_id
            WHERE library.torbox_file_id = file.id
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE library_entries AS library
            SET info_hash = LOWER(selection.info_hash)
            FROM torbox_files AS file
            JOIN torbox_items AS item ON item.id = file.torbox_item_id
            JOIN stream_selections AS selection
              ON selection.torbox_torrent_id = item.external_id
            WHERE library.torbox_file_id = file.id
              AND item.kind = 'torrents'
              AND selection.status = 'selected'
              AND selection.info_hash IS NOT NULL
            """
        )
    )

    op.drop_constraint(
        "fk_library_entries_torbox_file_id_torbox_files",
        "library_entries",
        type_="foreignkey",
    )
    op.alter_column("library_entries", "torbox_file_id", nullable=True)
    op.create_foreign_key(
        "fk_library_entries_torbox_file_id_torbox_files",
        "library_entries",
        "torbox_files",
        ["torbox_file_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM library_entries WHERE torbox_file_id IS NULL"))
    op.drop_constraint(
        "fk_library_entries_torbox_file_id_torbox_files",
        "library_entries",
        type_="foreignkey",
    )
    op.alter_column("library_entries", "torbox_file_id", nullable=False)
    op.create_foreign_key(
        "fk_library_entries_torbox_file_id_torbox_files",
        "library_entries",
        "torbox_files",
        ["torbox_file_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.drop_index("ix_library_entries_info_hash", table_name="library_entries")
    for column in (
        "source_file_size",
        "source_file_mime_type",
        "source_file_path",
        "source_file_name",
        "source_file_id",
        "source_item_name",
        "source_item_id",
        "source_kind",
        "info_hash",
    ):
        op.drop_column("library_entries", column)
