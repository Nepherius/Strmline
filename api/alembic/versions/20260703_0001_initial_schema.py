"""Initial schema.

Revision ID: 0001
Revises:
Create Date: 2026-07-03 00:00:00.000000+00:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("value", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("is_secret", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_app_settings")),
    )
    op.create_table(
        "media_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("media_type", sa.String(length=20), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("tmdb_id", sa.String(length=40), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_media_items")),
    )
    op.create_index(
        "ix_media_items_type_title",
        "media_items",
        ["media_type", "title"],
        unique=False,
    )
    op.create_table(
        "provider_credentials",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("credential_name", sa.String(length=100), nullable=False),
        sa.Column("encrypted_value", sa.Text(), nullable=False),
        sa.Column("secret_hint", sa.String(length=20), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_provider_credentials")),
        sa.UniqueConstraint(
            "provider",
            "credential_name",
            name="uq_provider_credentials_name",
        ),
    )
    op.create_table(
        "resolver_tokens",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("label", sa.String(length=100), nullable=False),
        sa.Column("token_hash", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_resolver_tokens")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_resolver_tokens_token_hash")),
    )
    op.create_index(
        "ix_resolver_tokens_revoked_at",
        "resolver_tokens",
        ["revoked_at"],
        unique=False,
    )
    op.create_table(
        "sync_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scanned_count", sa.Integer(), nullable=False),
        sa.Column("written_count", sa.Integer(), nullable=False),
        sa.Column("skipped_count", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sync_runs")),
    )
    op.create_index(
        "ix_sync_runs_status_started_at",
        "sync_runs",
        ["status", "started_at"],
        unique=False,
    )
    op.create_table(
        "torbox_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("external_id", sa.String(length=100), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_torbox_items")),
        sa.UniqueConstraint(
            "kind",
            "external_id",
            name="uq_torbox_items_kind_external_id",
        ),
    )
    op.create_index("ix_torbox_items_kind", "torbox_items", ["kind"], unique=False)
    op.create_table(
        "library_entries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("opaque_id", sa.String(length=64), nullable=False),
        sa.Column("media_item_id", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(length=20), nullable=False),
        sa.Column("season_number", sa.Integer(), nullable=True),
        sa.Column("episode_number", sa.Integer(), nullable=True),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("provider_item_id", sa.String(length=100), nullable=False),
        sa.Column("provider_file_id", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["media_item_id"],
            ["media_items.id"],
            name=op.f("fk_library_entries_media_item_id_media_items"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_library_entries")),
        sa.UniqueConstraint("opaque_id", name="uq_library_entries_opaque_id"),
    )
    op.create_index(
        "ix_library_entries_category",
        "library_entries",
        ["category"],
        unique=False,
    )
    op.create_table(
        "sync_errors",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("sync_run_id", sa.Integer(), nullable=False),
        sa.Column("phase", sa.String(length=60), nullable=False),
        sa.Column("item_ref", sa.String(length=200), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["sync_run_id"],
            ["sync_runs.id"],
            name=op.f("fk_sync_errors_sync_run_id_sync_runs"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sync_errors")),
    )
    op.create_index("ix_sync_errors_sync_run_id", "sync_errors", ["sync_run_id"], unique=False)
    op.create_table(
        "generated_files",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("library_entry_id", sa.Integer(), nullable=False),
        sa.Column("relative_path", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=128), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["library_entry_id"],
            ["library_entries.id"],
            name=op.f("fk_generated_files_library_entry_id_library_entries"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_generated_files")),
        sa.UniqueConstraint("relative_path", name="uq_generated_files_relative_path"),
    )
    op.create_index(
        "ix_generated_files_library_entry_id",
        "generated_files",
        ["library_entry_id"],
        unique=False,
    )
    op.create_table(
        "playback_attempts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("library_entry_id", sa.Integer(), nullable=True),
        sa.Column("entry_opaque_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["library_entry_id"],
            ["library_entries.id"],
            name=op.f("fk_playback_attempts_library_entry_id_library_entries"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_playback_attempts")),
    )
    op.create_index(
        "ix_playback_attempts_library_entry_created",
        "playback_attempts",
        ["library_entry_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_playback_attempts_library_entry_created", table_name="playback_attempts")
    op.drop_table("playback_attempts")
    op.drop_index("ix_generated_files_library_entry_id", table_name="generated_files")
    op.drop_table("generated_files")
    op.drop_index("ix_sync_errors_sync_run_id", table_name="sync_errors")
    op.drop_table("sync_errors")
    op.drop_index("ix_library_entries_category", table_name="library_entries")
    op.drop_table("library_entries")
    op.drop_index("ix_torbox_items_kind", table_name="torbox_items")
    op.drop_table("torbox_items")
    op.drop_index("ix_sync_runs_status_started_at", table_name="sync_runs")
    op.drop_table("sync_runs")
    op.drop_index("ix_resolver_tokens_revoked_at", table_name="resolver_tokens")
    op.drop_table("resolver_tokens")
    op.drop_table("provider_credentials")
    op.drop_index("ix_media_items_type_title", table_name="media_items")
    op.drop_table("media_items")
    op.drop_table("app_settings")
