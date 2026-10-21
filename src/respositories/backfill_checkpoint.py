"""Database access for historical-backfill checkpoints."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.models.historical_backfill import HistoricalBackfillCheckpoint


class BackfillCheckpointRepository:
    def __init__(self, session: Session):
        self.session = session

    def get(self, job_id: str) -> HistoricalBackfillCheckpoint | None:
        statement = select(HistoricalBackfillCheckpoint).where(
            HistoricalBackfillCheckpoint.job_id == job_id
        )
        return self.session.scalar(statement)

    def create(self, checkpoint: HistoricalBackfillCheckpoint) -> HistoricalBackfillCheckpoint:
        self.session.add(checkpoint)
        self.session.commit()
        self.session.refresh(checkpoint)
        return checkpoint

    def save(self, checkpoint: HistoricalBackfillCheckpoint) -> HistoricalBackfillCheckpoint:
        saved = self.session.merge(checkpoint)
        self.session.commit()
        self.session.refresh(saved)
        return saved
