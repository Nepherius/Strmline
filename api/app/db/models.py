from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    is_secret: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )


class ProviderCredential(Base):
    __tablename__ = "provider_credentials"
    __table_args__ = (
        UniqueConstraint("provider", "credential_name", name="uq_provider_credentials_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    credential_name: Mapped[str] = mapped_column(String(100), nullable=False)
    encrypted_value: Mapped[str] = mapped_column(Text, nullable=False)
    secret_hint: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )


class TorBoxItem(Base):
    __tablename__ = "torbox_items"
    __table_args__ = (
        UniqueConstraint("kind", "external_id", name="uq_torbox_items_kind_external_id"),
        Index("ix_torbox_items_kind", "kind"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    external_id: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )


class TmdbCacheEntry(Base):
    __tablename__ = "tmdb_cache_entries"
    __table_args__ = (
        UniqueConstraint("cache_key", name="uq_tmdb_cache_entries_cache_key"),
        Index("ix_tmdb_cache_entries_expires_at", "expires_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cache_key: Mapped[str] = mapped_column(String(255), nullable=False)
    endpoint: Mapped[str] = mapped_column(Text, nullable=False)
    request_params: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    response_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AniListCacheEntry(Base):
    __tablename__ = "anilist_cache_entries"
    __table_args__ = (
        UniqueConstraint("cache_key", name="uq_anilist_cache_entries_cache_key"),
        Index("ix_anilist_cache_entries_expires_at", "expires_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cache_key: Mapped[str] = mapped_column(String(255), nullable=False)
    operation_name: Mapped[str] = mapped_column(String(100), nullable=False)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    variables: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    response_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class StreamSelection(Base):
    __tablename__ = "stream_selections"
    __table_args__ = (
        UniqueConstraint("stream_key", name="uq_stream_selections_stream_key"),
        Index("ix_stream_selections_info_hash", "info_hash"),
        Index("ix_stream_selections_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stream_key: Mapped[str] = mapped_column(String(64), nullable=False)
    media_type: Mapped[str] = mapped_column(String(20), nullable=False)
    media_id: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    source_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    info_hash: Mapped[str | None] = mapped_column(String(100), nullable=True)
    torbox_torrent_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="selected", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )


class LibraryExclusion(Base):
    __tablename__ = "library_exclusions"
    __table_args__ = (
        UniqueConstraint("relative_prefix", name="uq_library_exclusions_relative_prefix"),
        Index("ix_library_exclusions_category", "category"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    category: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    relative_prefix: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )


class ClassificationOverride(Base):
    __tablename__ = "classification_overrides"
    __table_args__ = (
        UniqueConstraint("source_prefix", name="uq_classification_overrides_source_prefix"),
        Index("ix_classification_overrides_target_category", "target_category"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_category: Mapped[str] = mapped_column(String(20), nullable=False)
    source_prefix: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    target_category: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )


class MediaItem(Base):
    __tablename__ = "media_items"
    __table_args__ = (
        Index("ix_media_items_type_title", "media_type", "title"),
        Index(
            "ix_media_items_tmdb_id",
            "tmdb_id",
            unique=True,
            postgresql_where=text("tmdb_id IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    media_type: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tmdb_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    library_entries: Mapped[list[LibraryEntry]] = relationship(back_populates="media_item")


class LibraryEntry(Base):
    __tablename__ = "library_entries"
    __table_args__ = (
        UniqueConstraint("opaque_id", name="uq_library_entries_opaque_id"),
        Index("ix_library_entries_category", "category"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    opaque_id: Mapped[str] = mapped_column(String(64), nullable=False)
    media_item_id: Mapped[int] = mapped_column(ForeignKey("media_items.id"), nullable=False)
    category: Mapped[str] = mapped_column(String(20), nullable=False)
    season_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    episode_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    provider_item_id: Mapped[str] = mapped_column(String(100), nullable=False)
    provider_file_id: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    media_item: Mapped[MediaItem] = relationship(back_populates="library_entries")
    generated_files: Mapped[list[GeneratedFile]] = relationship(back_populates="library_entry")
    playback_attempts: Mapped[list[PlaybackAttempt]] = relationship(back_populates="library_entry")


class GeneratedFile(Base):
    __tablename__ = "generated_files"
    __table_args__ = (
        UniqueConstraint("relative_path", name="uq_generated_files_relative_path"),
        Index("ix_generated_files_library_entry_id", "library_entry_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    library_entry_id: Mapped[int] = mapped_column(ForeignKey("library_entries.id"), nullable=False)
    relative_path: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    library_entry: Mapped[LibraryEntry] = relationship(back_populates="generated_files")


class SyncRun(Base):
    __tablename__ = "sync_runs"
    __table_args__ = (
        Index("ix_sync_runs_status_started_at", "status", "started_at"),
        Index("ix_sync_runs_source_started_at", "source", "started_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    source: Mapped[str] = mapped_column(String(30), default="manual", nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    scanned_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    written_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    skipped_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    errors: Mapped[list[SyncError]] = relationship(back_populates="sync_run")


class SyncError(Base):
    __tablename__ = "sync_errors"
    __table_args__ = (
        Index("ix_sync_errors_sync_run_id", "sync_run_id"),
        Index("ix_sync_errors_dismissed_created_at", "dismissed_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sync_run_id: Mapped[int] = mapped_column(ForeignKey("sync_runs.id"), nullable=False)
    phase: Mapped[str] = mapped_column(String(60), nullable=False)
    item_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    sync_run: Mapped[SyncRun] = relationship(back_populates="errors")


class ResolverToken(Base):
    __tablename__ = "resolver_tokens"
    __table_args__ = (Index("ix_resolver_tokens_revoked_at", "revoked_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PlaybackAttempt(Base):
    __tablename__ = "playback_attempts"
    __table_args__ = (
        Index("ix_playback_attempts_library_entry_created", "library_entry_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    library_entry_id: Mapped[int | None] = mapped_column(
        ForeignKey("library_entries.id"),
        nullable=True,
    )
    entry_opaque_id: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    library_entry: Mapped[LibraryEntry | None] = relationship(back_populates="playback_attempts")
