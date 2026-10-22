"""Repository for compatible, exact-version paper briefs."""

from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.models.paper_brief import PaperBrief


class PaperBriefRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_compatible(
        self, *, arxiv_id: str, model: str, prompt_version: str,
        retrieval_mode: str, top_k: int, evidence_hash: str,
    ) -> Optional[PaperBrief]:
        stmt = select(PaperBrief).where(
            PaperBrief.arxiv_id == arxiv_id,
            PaperBrief.model == model,
            PaperBrief.prompt_version == prompt_version,
            PaperBrief.retrieval_mode == retrieval_mode,
            PaperBrief.top_k == top_k,
            PaperBrief.evidence_hash == evidence_hash,
        )
        return self.session.scalar(stmt)

    def save(
        self, *, arxiv_id: str, content: dict[str, Any], model: str,
        prompt_version: str, retrieval_mode: str, top_k: int, evidence_hash: str,
    ) -> PaperBrief:
        existing = self.get_compatible(
            arxiv_id=arxiv_id, model=model, prompt_version=prompt_version,
            retrieval_mode=retrieval_mode, top_k=top_k, evidence_hash=evidence_hash,
        )
        if existing:
            existing.content = content
            self.session.add(existing)
            self.session.commit()
            self.session.refresh(existing)
            return existing

        record = PaperBrief(
            arxiv_id=arxiv_id, content=content, model=model, prompt_version=prompt_version,
            retrieval_mode=retrieval_mode, top_k=top_k, evidence_hash=evidence_hash,
        )
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return record
