# pyright: reportImportCycles=false
from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models import LibraryEntry


def _utc_now() -> datetime:
    return datetime.now(UTC)


class MediaItem(Base):
    __tablename__ = "media_items"
    __table_args__ = (
        CheckConstraint(
            "content_kind IN ('movie', 'series')",
            name="ck_media_items_content_kind",
        ),
        CheckConstraint(
            "library_category IN ('movies', 'shows', 'anime')",
            name="ck_media_items_library_category",
        ),
        CheckConstraint(
            "year IS NULL OR year BETWEEN 1800 AND 3000",
            name="ck_media_items_year",
        ),
        Index("ix_media_items_kind_title", "content_kind", "title"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    content_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    library_category: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    poster_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utc_now,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utc_now,
        onupdate=_utc_now,
        nullable=False,
    )

    library_entries: Mapped[list[LibraryEntry]] = relationship(back_populates="media_item")
    external_identities: Mapped[list[MediaExternalIdentity]] = relationship(
        back_populates="media_item",
        cascade="all, delete-orphan",
    )
    source_bindings: Mapped[list[SourceMediaBinding]] = relationship(
        back_populates="media_item",
        cascade="all, delete-orphan",
    )
    aliases: Mapped[list[MediaAlias]] = relationship(
        back_populates="media_item",
        cascade="all, delete-orphan",
    )


class MediaExternalIdentity(Base):
    __tablename__ = "media_external_identities"
    __table_args__ = (
        CheckConstraint(
            "provider_media_kind IN ('movie', 'tv')",
            name="ck_media_external_identities_provider_kind",
        ),
        CheckConstraint(
            "confidence IS NULL OR confidence BETWEEN 0 AND 100",
            name="ck_media_external_identities_confidence",
        ),
        UniqueConstraint(
            "provider",
            "provider_media_kind",
            "external_id",
            name="uq_media_external_identities_provider_kind_id",
        ),
        UniqueConstraint(
            "media_item_id",
            "provider",
            name="uq_media_external_identities_media_provider",
        ),
        Index("ix_media_external_identities_media_item_id", "media_item_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    media_item_id: Mapped[int] = mapped_column(
        ForeignKey("media_items.id", ondelete="CASCADE"),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    provider_media_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    external_id: Mapped[str] = mapped_column(String(100), nullable=False)
    authority: Mapped[str] = mapped_column(String(30), nullable=False)
    authoritative: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    confidence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    resolver_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, onupdate=_utc_now, nullable=False
    )

    media_item: Mapped[MediaItem] = relationship(back_populates="external_identities")


class SourceMediaBinding(Base):
    __tablename__ = "source_media_bindings"
    __table_args__ = (
        CheckConstraint(
            "source_kind IN ('torrents', 'usenet', 'webdl')",
            name="ck_source_media_bindings_source_kind",
        ),
        CheckConstraint(
            "info_hash IS NULL OR info_hash = LOWER(info_hash)",
            name="ck_source_media_bindings_info_hash_normalized",
        ),
        CheckConstraint(
            "confidence IS NULL OR confidence BETWEEN 0 AND 100",
            name="ck_source_media_bindings_confidence",
        ),
        Index(
            "uq_source_media_bindings_source_item",
            "source_kind",
            "source_item_id",
            unique=True,
            postgresql_where=text("source_item_id IS NOT NULL"),
        ),
        Index(
            "uq_source_media_bindings_info_hash",
            "info_hash",
            unique=True,
            postgresql_where=text("info_hash IS NOT NULL"),
        ),
        Index("ix_source_media_bindings_media_item_id", "media_item_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    media_item_id: Mapped[int] = mapped_column(
        ForeignKey("media_items.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    source_item_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    info_hash: Mapped[str | None] = mapped_column(String(100), nullable=True)
    authority: Mapped[str] = mapped_column(String(30), nullable=False)
    authoritative: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    confidence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    resolver_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    resolved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, onupdate=_utc_now, nullable=False
    )

    media_item: Mapped[MediaItem] = relationship(back_populates="source_bindings")


class MediaAlias(Base):
    __tablename__ = "media_aliases"
    __table_args__ = (
        CheckConstraint(
            "content_kind IN ('movie', 'series')",
            name="ck_media_aliases_content_kind",
        ),
        UniqueConstraint(
            "media_item_id",
            "normalized_alias",
            name="uq_media_aliases_media_normalized",
        ),
        Index(
            "ix_media_aliases_kind_normalized",
            "content_kind",
            "normalized_alias",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    media_item_id: Mapped[int] = mapped_column(
        ForeignKey("media_items.id", ondelete="CASCADE"),
        nullable=False,
    )
    content_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    alias: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_alias: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(30), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, nullable=False
    )

    media_item: Mapped[MediaItem] = relationship(back_populates="aliases")
