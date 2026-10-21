"""Persistent progress for manually run historical metadata backfills."""

from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.db.interfaces.postgresql import Base


class HistoricalBackfillCheckpoint(Base):
    __tablename__ = "historical_backfill_checkpoints"

    job_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    categories: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    window_days: Mapped[int] = mapped_column(Integer, nullable=False)
    page_size: Mapped[int] = mapped_column(Integer, nullable=False)
    current_window_start: Mapped[date] = mapped_column(Date, nullable=False)
    current_window_end: Mapped[date] = mapped_column(Date, nullable=False)
    next_offset: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    papers_fetched: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    papers_stored: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class MetadataIndexSyncCheckpoint(Base):
    """Independent cursor for PostgreSQL-to-OpenSearch metadata synchronization."""

    __tablename__ = "metadata_index_sync_checkpoints"

    job_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    last_arxiv_id: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    records_indexed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
