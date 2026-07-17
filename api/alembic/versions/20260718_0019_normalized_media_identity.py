"""Normalize external media identity and persist source bindings.

Revision ID: 20260718_0019
Revises: 20260717_0018
Create Date: 2026-07-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260718_0019"
down_revision: str | None = "20260717_0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "stream_selections",
        sa.Column(
            "identity_authority",
            sa.String(30),
            server_default="search_confirmed",
            nullable=False,
        ),
    )
    op.add_column("media_items", sa.Column("content_kind", sa.String(20), nullable=True))
    op.add_column("media_items", sa.Column("library_category", sa.String(20), nullable=True))
    op.add_column("media_items", sa.Column("poster_path", sa.Text(), nullable=True))
    op.add_column("media_items", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))
    op.execute(
        sa.text(
            """
            UPDATE media_items
            SET content_kind = CASE WHEN media_type = 'movies' THEN 'movie' ELSE 'series' END,
                library_category = media_type,
                updated_at = created_at
            """
        )
    )
    op.alter_column("media_items", "content_kind", nullable=False)
    op.alter_column("media_items", "library_category", nullable=False)
    op.alter_column("media_items", "updated_at", nullable=False)
    op.create_check_constraint(
        "ck_media_items_content_kind",
        "media_items",
        "content_kind IN ('movie', 'series')",
    )
    op.create_check_constraint(
        "ck_media_items_library_category",
        "media_items",
        "library_category IN ('movies', 'shows', 'anime')",
    )
    op.create_check_constraint(
        "ck_media_items_year",
        "media_items",
        "year IS NULL OR year BETWEEN 1800 AND 3000",
    )
    op.create_index(
        "ix_media_items_kind_title",
        "media_items",
        ["content_kind", "title"],
    )

    _create_external_identities()
    _create_source_bindings()
    _create_media_aliases()
    _backfill_identity_data()

    op.drop_index("ix_media_items_tmdb_id", table_name="media_items")
    op.drop_index("ix_media_items_type_title", table_name="media_items")
    op.drop_column("media_items", "tmdb_id_locked")
    op.drop_column("media_items", "tmdb_id")
    op.drop_column("media_items", "media_type")
    _add_domain_constraints()


def downgrade() -> None:
    _drop_domain_constraints()
    op.add_column("media_items", sa.Column("media_type", sa.String(20), nullable=True))
    op.add_column("media_items", sa.Column("tmdb_id", sa.String(40), nullable=True))
    op.add_column(
        "media_items",
        sa.Column("tmdb_id_locked", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.execute(
        sa.text(
            """
            UPDATE media_items AS media
            SET media_type = media.library_category,
                tmdb_id = identity.external_id,
                tmdb_id_locked = COALESCE(identity.authoritative, FALSE)
            FROM media_external_identities AS identity
            WHERE identity.media_item_id = media.id
              AND identity.provider = 'tmdb'
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE media_items
            SET media_type = library_category
            WHERE media_type IS NULL
            """
        )
    )
    op.alter_column("media_items", "media_type", nullable=False)
    op.create_index("ix_media_items_type_title", "media_items", ["media_type", "title"])
    op.create_index(
        "ix_media_items_tmdb_id",
        "media_items",
        ["tmdb_id"],
        unique=True,
        postgresql_where=sa.text("tmdb_id IS NOT NULL"),
    )

    op.drop_table("media_aliases")
    op.drop_table("source_media_bindings")
    op.drop_table("media_external_identities")
    op.drop_index("ix_media_items_kind_title", table_name="media_items")
    op.drop_constraint("ck_media_items_content_kind", "media_items", type_="check")
    op.drop_constraint("ck_media_items_library_category", "media_items", type_="check")
    op.drop_constraint("ck_media_items_year", "media_items", type_="check")
    op.drop_column("media_items", "updated_at")
    op.drop_column("media_items", "poster_path")
    op.drop_column("media_items", "content_kind")
    op.drop_column("media_items", "library_category")
    op.drop_column("stream_selections", "identity_authority")


def _create_external_identities() -> None:
    op.create_table(
        "media_external_identities",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("media_item_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(30), nullable=False),
        sa.Column("provider_media_kind", sa.String(20), nullable=False),
        sa.Column("external_id", sa.String(100), nullable=False),
        sa.Column("authority", sa.String(30), nullable=False),
        sa.Column("authoritative", sa.Boolean(), nullable=False),
        sa.Column("confidence", sa.Integer(), nullable=True),
        sa.Column("resolver_version", sa.String(40), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "provider_media_kind IN ('movie', 'tv')",
            name="ck_media_external_identities_provider_kind",
        ),
        sa.CheckConstraint(
            "confidence IS NULL OR confidence BETWEEN 0 AND 100",
            name="ck_media_external_identities_confidence",
        ),
        sa.ForeignKeyConstraint(
            ["media_item_id"],
            ["media_items.id"],
            name=op.f("fk_media_external_identities_media_item_id_media_items"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_media_external_identities")),
        sa.UniqueConstraint(
            "provider",
            "provider_media_kind",
            "external_id",
            name="uq_media_external_identities_provider_kind_id",
        ),
        sa.UniqueConstraint(
            "media_item_id",
            "provider",
            name="uq_media_external_identities_media_provider",
        ),
    )
    op.create_index(
        "ix_media_external_identities_media_item_id",
        "media_external_identities",
        ["media_item_id"],
    )


def _create_source_bindings() -> None:
    op.create_table(
        "source_media_bindings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("media_item_id", sa.Integer(), nullable=False),
        sa.Column("source_kind", sa.String(20), nullable=False),
        sa.Column("source_item_id", sa.String(100), nullable=True),
        sa.Column("info_hash", sa.String(100), nullable=True),
        sa.Column("authority", sa.String(30), nullable=False),
        sa.Column("authoritative", sa.Boolean(), nullable=False),
        sa.Column("confidence", sa.Integer(), nullable=True),
        sa.Column("resolver_version", sa.String(40), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "source_kind IN ('torrents', 'usenet', 'webdl')",
            name="ck_source_media_bindings_source_kind",
        ),
        sa.CheckConstraint(
            "info_hash IS NULL OR info_hash = LOWER(info_hash)",
            name="ck_source_media_bindings_info_hash_normalized",
        ),
        sa.CheckConstraint(
            "confidence IS NULL OR confidence BETWEEN 0 AND 100",
            name="ck_source_media_bindings_confidence",
        ),
        sa.ForeignKeyConstraint(
            ["media_item_id"],
            ["media_items.id"],
            name=op.f("fk_source_media_bindings_media_item_id_media_items"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_source_media_bindings")),
    )
    op.create_index(
        "uq_source_media_bindings_source_item",
        "source_media_bindings",
        ["source_kind", "source_item_id"],
        unique=True,
        postgresql_where=sa.text("source_item_id IS NOT NULL"),
    )
    op.create_index(
        "uq_source_media_bindings_info_hash",
        "source_media_bindings",
        ["info_hash"],
        unique=True,
        postgresql_where=sa.text("info_hash IS NOT NULL"),
    )
    op.create_index(
        "ix_source_media_bindings_media_item_id",
        "source_media_bindings",
        ["media_item_id"],
    )


def _create_media_aliases() -> None:
    op.create_table(
        "media_aliases",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("media_item_id", sa.Integer(), nullable=False),
        sa.Column("content_kind", sa.String(20), nullable=False),
        sa.Column("alias", sa.Text(), nullable=False),
        sa.Column("normalized_alias", sa.Text(), nullable=False),
        sa.Column("source", sa.String(30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "content_kind IN ('movie', 'series')",
            name="ck_media_aliases_content_kind",
        ),
        sa.ForeignKeyConstraint(
            ["media_item_id"],
            ["media_items.id"],
            name=op.f("fk_media_aliases_media_item_id_media_items"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_media_aliases")),
        sa.UniqueConstraint(
            "media_item_id",
            "normalized_alias",
            name="uq_media_aliases_media_normalized",
        ),
    )
    op.create_index(
        "ix_media_aliases_kind_normalized",
        "media_aliases",
        ["content_kind", "normalized_alias"],
    )


def _backfill_identity_data() -> None:
    op.execute(
        sa.text(
            """
            INSERT INTO media_external_identities (
                media_item_id, provider, provider_media_kind, external_id, authority,
                authoritative, confidence, resolver_version, created_at, updated_at
            )
            SELECT id,
                   'tmdb',
                   CASE WHEN media_type = 'movies' THEN 'movie' ELSE 'tv' END,
                   tmdb_id,
                   CASE WHEN tmdb_id_locked THEN 'manual' ELSE 'migrated' END,
                   tmdb_id_locked,
                   CASE WHEN tmdb_id_locked THEN 100 ELSE NULL END,
                   'legacy-v1',
                   created_at,
                   COALESCE(updated_at, created_at)
            FROM media_items
            WHERE tmdb_id IS NOT NULL
            """
        )
    )
    op.execute(
        sa.text(
            """
            INSERT INTO media_aliases (
                media_item_id, content_kind, alias, normalized_alias, source, created_at
            )
            SELECT id,
                   content_kind,
                   title,
                   TRIM(LOWER(REGEXP_REPLACE(title, '[^[:alnum:]]+', ' ', 'g'))),
                   'canonical',
                   created_at
            FROM media_items
            WHERE TRIM(title) <> ''
            ON CONFLICT DO NOTHING
            """
        )
    )
    op.execute(
        sa.text(
            """
            INSERT INTO source_media_bindings (
                media_item_id, source_kind, source_item_id, info_hash, authority,
                authoritative, confidence, resolver_version, resolved_at, updated_at
            )
            SELECT DISTINCT ON (entry.source_kind, entry.source_item_id)
                   entry.media_item_id,
                   entry.source_kind,
                   entry.source_item_id,
                   NULL,
                   CASE WHEN identity.authoritative THEN identity.authority ELSE 'migrated' END,
                   COALESCE(identity.authoritative, FALSE),
                   identity.confidence,
                   'legacy-v1',
                   entry.created_at,
                   entry.updated_at
            FROM library_entries AS entry
            LEFT JOIN media_external_identities AS identity
              ON identity.media_item_id = entry.media_item_id AND identity.provider = 'tmdb'
            WHERE entry.source_kind IN ('torrents', 'usenet', 'webdl')
              AND entry.source_item_id IS NOT NULL
            ORDER BY entry.source_kind,
                     entry.source_item_id,
                     COALESCE(identity.authoritative, FALSE) DESC,
                     entry.updated_at DESC,
                     entry.id
            """
        )
    )
    op.execute(
        sa.text(
            """
            INSERT INTO source_media_bindings (
                media_item_id, source_kind, source_item_id, info_hash, authority,
                authoritative, confidence, resolver_version, resolved_at, updated_at
            )
            SELECT DISTINCT ON (LOWER(entry.info_hash))
                   entry.media_item_id,
                   COALESCE(NULLIF(entry.source_kind, ''), 'torrents'),
                   NULL,
                   LOWER(entry.info_hash),
                   CASE WHEN identity.authoritative THEN identity.authority ELSE 'migrated' END,
                   COALESCE(identity.authoritative, FALSE),
                   identity.confidence,
                   'legacy-v1',
                   entry.created_at,
                   entry.updated_at
            FROM library_entries AS entry
            LEFT JOIN media_external_identities AS identity
              ON identity.media_item_id = entry.media_item_id AND identity.provider = 'tmdb'
            WHERE entry.info_hash IS NOT NULL
            ORDER BY LOWER(entry.info_hash),
                     COALESCE(identity.authoritative, FALSE) DESC,
                     entry.updated_at DESC,
                     entry.id
            """
        )
    )


def _add_domain_constraints() -> None:
    op.create_check_constraint(
        "ck_application_settings_playback_mode",
        "application_settings",
        "playback_mode IN ('direct', 'resolver')",
    )
    op.create_check_constraint(
        "ck_application_settings_sync_interval_positive",
        "application_settings",
        "sync_interval_minutes > 0",
    )
    op.create_check_constraint(
        "ck_stream_selections_media_type",
        "stream_selections",
        "media_type IN ('movie', 'series')",
    )
    op.create_check_constraint(
        "ck_stream_selections_status",
        "stream_selections",
        "status IN ('selected')",
    )
    op.create_check_constraint(
        "ck_stream_selections_media_year",
        "stream_selections",
        "media_year IS NULL OR media_year BETWEEN 1800 AND 3000",
    )
    op.create_check_constraint(
        "ck_library_entries_category",
        "library_entries",
        "category IN ('movies', 'shows', 'anime')",
    )
    op.create_check_constraint(
        "ck_library_entries_season_nonnegative",
        "library_entries",
        "season_number IS NULL OR season_number >= 0",
    )
    op.create_check_constraint(
        "ck_library_entries_episode_nonnegative",
        "library_entries",
        "episode_number IS NULL OR episode_number >= 0",
    )
    # Preserve every legacy row while removing duplicated denormalized source keys.
    # The normalized TorBox relation and generated-file relation remain intact.
    op.execute(
        sa.text(
            """
            WITH duplicate_sources AS (
                SELECT id,
                       ROW_NUMBER() OVER (
                           PARTITION BY source_kind, source_item_id, source_file_id
                           ORDER BY updated_at DESC, id DESC
                       ) AS position
                FROM library_entries
                WHERE source_kind IS NOT NULL
                  AND source_item_id IS NOT NULL
                  AND source_file_id IS NOT NULL
            )
            UPDATE library_entries AS entry
            SET source_file_id = NULL
            FROM duplicate_sources AS duplicate
            WHERE entry.id = duplicate.id AND duplicate.position > 1
            """
        )
    )
    op.create_index(
        "uq_library_entries_source_file",
        "library_entries",
        ["source_kind", "source_item_id", "source_file_id"],
        unique=True,
        postgresql_where=sa.text(
            "source_kind IS NOT NULL AND source_item_id IS NOT NULL "
            "AND source_file_id IS NOT NULL"
        ),
    )
    op.create_check_constraint(
        "ck_sync_runs_status",
        "sync_runs",
        "status IN ('success', 'failed', 'partial')",
    )
    op.create_check_constraint(
        "ck_sync_runs_source",
        "sync_runs",
        "source IN ('manual', 'auto', 'season_auto_complete')",
    )
    op.create_check_constraint(
        "ck_watchlist_items_media_type",
        "watchlist_items",
        "media_type IN ('movie', 'series')",
    )


def _drop_domain_constraints() -> None:
    op.drop_constraint(
        "ck_watchlist_items_media_type", "watchlist_items", type_="check"
    )
    op.drop_constraint("ck_sync_runs_source", "sync_runs", type_="check")
    op.drop_constraint("ck_sync_runs_status", "sync_runs", type_="check")
    op.drop_index("uq_library_entries_source_file", table_name="library_entries")
    op.drop_constraint(
        "ck_library_entries_episode_nonnegative", "library_entries", type_="check"
    )
    op.drop_constraint(
        "ck_library_entries_season_nonnegative", "library_entries", type_="check"
    )
    op.drop_constraint(
        "ck_library_entries_category", "library_entries", type_="check"
    )
    op.drop_constraint(
        "ck_stream_selections_media_year", "stream_selections", type_="check"
    )
    op.drop_constraint(
        "ck_stream_selections_status", "stream_selections", type_="check"
    )
    op.drop_constraint(
        "ck_stream_selections_media_type", "stream_selections", type_="check"
    )
    op.drop_constraint(
        "ck_application_settings_sync_interval_positive",
        "application_settings",
        type_="check",
    )
    op.drop_constraint(
        "ck_application_settings_playback_mode",
        "application_settings",
        type_="check",
    )
