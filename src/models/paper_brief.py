"""Persisted, versioned paper-specific Deep Dive briefs."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, JSON, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from src.db.interfaces.postgresql import Base


class PaperBrief(Base):
    __tablename__ = "paper_briefs"
    __table_args__ = (
        UniqueConstraint(
            "arxiv_id", "model", "prompt_version", "retrieval_mode", "top_k", "evidence_hash",
            name="uq_paper_brief_compatible_generation",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    arxiv_id = Column(String, nullable=False, index=True)
    content = Column(JSON, nullable=False)
    model = Column(String, nullable=False)
    prompt_version = Column(String, nullable=False)
    retrieval_mode = Column(String, nullable=False)
    top_k = Column(Integer, nullable=False)
    evidence_hash = Column(String(64), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc), nullable=False,
    )
