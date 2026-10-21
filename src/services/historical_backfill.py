"""Bounded, resumable, metadata-only arXiv historical backfill."""

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Optional

from dateutil import parser as date_parser
from sqlalchemy.orm import Session

from src.config import get_settings
from src.models.historical_backfill import HistoricalBackfillCheckpoint
from src.respositories.backfill_checkpoint import BackfillCheckpointRepository
from src.respositories.paper import PaperRepository
from src.schema.arxiv.paper import ArxivPaper, PaperCreate
from src.services.arxiv.client import ArxivClient

logger = logging.getLogger(__name__)

MAX_PAGE_SIZE = 2000
MAX_WINDOW_DAYS = 365
MAX_PAGES_PER_EXECUTION = 100


class HistoricalMetadataBackfillService:
    """Fetch and upsert bounded pages of arXiv metadata without PDF/index work."""

    def __init__(
        self,
        arxiv_client: ArxivClient,
        database: Any,
        paper_repository_factory: Callable[[Session], PaperRepository] = PaperRepository,
        checkpoint_repository_factory: Callable[[Session], BackfillCheckpointRepository] = BackfillCheckpointRepository,
    ):
        self.arxiv_client = arxiv_client
        self.database = database
        self.paper_repository_factory = paper_repository_factory
        self.checkpoint_repository_factory = checkpoint_repository_factory

    async def run(
        self,
        *,
        job_id: str,
        start_date: str,
        end_date: str,
        categories: Optional[list[str]] = None,
        window_days: int = 7,
        page_size: int = 100,
        max_pages: int = 5,
    ) -> dict[str, Any]:
        """Run at most ``max_pages`` sequential API pages and persist each cursor step.

        ``max_pages`` is an execution budget and may change when resuming. The
        date range, categories, window size, and page size define the cursor and
        must match the checkpoint; use a new job ID to start different work.
        """
        selected_categories = self._normalize_categories(categories)
        start = self._parse_date(start_date, "start_date")
        end = self._parse_date(end_date, "end_date")
        self._validate_options(job_id, start, end, window_days, page_size, max_pages)

        checkpoint = self._load_or_create_checkpoint(
            job_id, start, end, selected_categories, window_days, page_size
        )
        if checkpoint.status == "completed":
            return self._summary(checkpoint, pages_processed=0)

        checkpoint.status = "running"
        checkpoint.last_error = None
        checkpoint.updated_at = datetime.now(timezone.utc)
        checkpoint = self._save_checkpoint(checkpoint)

        pages_processed = 0
        current_stage = "arXiv page request"
        try:
            while pages_processed < max_pages and checkpoint.status != "completed":
                page = await self.arxiv_client.fetch_paperts(
                    max_results=page_size,
                    start=checkpoint.next_offset,
                    sort_by="submittedDate",
                    sort_order="ascending",
                    from_date=checkpoint.current_window_start.strftime("%Y%m%d"),
                    to_date=checkpoint.current_window_end.strftime("%Y%m%d"),
                    categories=selected_categories,
                )
                pages_processed += 1
                if len(page) > page_size:
                    raise RuntimeError(
                        f"arXiv returned {len(page)} records for a page size of {page_size}"
                    )

                # Page writes happen first. A partially committed page is safe to
                # replay because PaperRepository.upsert keys on exact arxiv_id.
                current_stage = "PostgreSQL page upsert"
                stored_count = self._store_page(page)

                checkpoint.papers_fetched += len(page)
                checkpoint.papers_stored += stored_count
                if len(page) < page_size:
                    self._advance_window(checkpoint)
                else:
                    checkpoint.next_offset += len(page)
                checkpoint.last_error = None
                checkpoint.updated_at = datetime.now(timezone.utc)
                current_stage = "checkpoint update"
                checkpoint = self._save_checkpoint(checkpoint)
                current_stage = "arXiv page request"

                logger.info(
                    "Backfill job %s: page %d stored (%d records); total stored=%d; status=%s",
                    job_id,
                    pages_processed,
                    stored_count,
                    checkpoint.papers_stored,
                    checkpoint.status,
                )

            if checkpoint.status != "completed":
                checkpoint.status = "paused"
                checkpoint.updated_at = datetime.now(timezone.utc)
                checkpoint = self._save_checkpoint(checkpoint)

            return self._summary(checkpoint, pages_processed)
        except Exception as exc:
            self._mark_failed(job_id, exc, current_stage)
            raise

    def _load_or_create_checkpoint(
        self,
        job_id: str,
        start: date,
        end: date,
        categories: list[str],
        window_days: int,
        page_size: int,
    ) -> HistoricalBackfillCheckpoint:
        with self.database.get_session() as session:
            repository = self.checkpoint_repository_factory(session)
            checkpoint = repository.get(job_id)
            if checkpoint is None:
                checkpoint = HistoricalBackfillCheckpoint(
                    job_id=job_id,
                    start_date=start,
                    end_date=end,
                    categories=categories,
                    window_days=window_days,
                    page_size=page_size,
                    current_window_start=start,
                    current_window_end=min(start + timedelta(days=window_days - 1), end),
                    next_offset=0,
                    status="pending",
                    papers_fetched=0,
                    papers_stored=0,
                    last_error=None,
                    updated_at=datetime.now(timezone.utc),
                )
                return repository.create(checkpoint)

            actual = (
                checkpoint.start_date,
                checkpoint.end_date,
                sorted(checkpoint.categories),
                checkpoint.window_days,
                checkpoint.page_size,
            )
            expected = (start, end, categories, window_days, page_size)
            if actual != expected:
                raise ValueError(
                    f"Job {job_id!r} already exists with different date/category/window/page settings; "
                    "choose a new job ID to start a separate backfill."
                )
            return checkpoint

    def _store_page(self, papers: list[ArxivPaper]) -> int:
        if not papers:
            return 0
        with self.database.get_session() as session:
            repository = self.paper_repository_factory(session)
            stored = 0
            for paper in papers:
                paper_data = PaperCreate(
                    arxiv_id=paper.arxiv_id,
                    title=paper.title,
                    authors=paper.authors,
                    abstract=paper.abstract,
                    categories=paper.categories,
                    published_date=date_parser.parse(paper.published_date),
                    pdf_url=paper.pdf_url,
                )
                if repository.upsert(paper_data) is None:
                    raise RuntimeError(f"Paper upsert returned no record for {paper.arxiv_id}")
                stored += 1
            return stored

    def _save_checkpoint(self, checkpoint: HistoricalBackfillCheckpoint) -> HistoricalBackfillCheckpoint:
        with self.database.get_session() as session:
            repository = self.checkpoint_repository_factory(session)
            return repository.save(checkpoint)

    def _mark_failed(self, job_id: str, error: Exception, stage: str) -> None:
        """Persist failure state without moving the durable cursor."""
        try:
            with self.database.get_session() as session:
                repository = self.checkpoint_repository_factory(session)
                checkpoint = repository.get(job_id)
                if checkpoint is None:
                    return
                checkpoint.status = "failed"
                checkpoint.last_error = f"{stage} failed ({type(error).__name__})"
                checkpoint.updated_at = datetime.now(timezone.utc)
                repository.save(checkpoint)
        except Exception as failure_error:
            logger.error(
                "Could not persist failure status for backfill job %s (%s)",
                job_id,
                type(failure_error).__name__,
            )

    @staticmethod
    def _advance_window(checkpoint: HistoricalBackfillCheckpoint) -> None:
        next_start = checkpoint.current_window_end + timedelta(days=1)
        checkpoint.next_offset = 0
        if next_start > checkpoint.end_date:
            checkpoint.status = "completed"
            return
        checkpoint.current_window_start = next_start
        checkpoint.current_window_end = min(
            next_start + timedelta(days=checkpoint.window_days - 1), checkpoint.end_date
        )

    def _normalize_categories(self, categories: Optional[list[str]]) -> list[str]:
        configured = categories if categories is not None else self.arxiv_client.search_categories
        normalized = sorted({category.strip() for category in configured if category.strip()})
        if not normalized:
            raise ValueError("At least one category is required for a historical backfill")
        return normalized

    @staticmethod
    def _parse_date(value: str, name: str) -> date:
        try:
            return datetime.strptime(value, "%Y%m%d").date()
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{name} must use YYYYMMDD format") from exc

    @staticmethod
    def _validate_options(
        job_id: str, start: date, end: date, window_days: int, page_size: int, max_pages: int
    ) -> None:
        if not job_id or len(job_id) > 160:
            raise ValueError("job_id must be a non-empty string of at most 160 characters")
        if start > end:
            raise ValueError("start_date must be on or before end_date")
        if not 1 <= window_days <= MAX_WINDOW_DAYS:
            raise ValueError(f"window_days must be between 1 and {MAX_WINDOW_DAYS}")
        if not 1 <= page_size <= MAX_PAGE_SIZE:
            raise ValueError(f"page_size must be between 1 and {MAX_PAGE_SIZE}")
        if not 1 <= max_pages <= MAX_PAGES_PER_EXECUTION:
            raise ValueError(f"max_pages must be between 1 and {MAX_PAGES_PER_EXECUTION}")

    @staticmethod
    def _summary(checkpoint: HistoricalBackfillCheckpoint, pages_processed: int) -> dict[str, Any]:
        return {
            "job_id": checkpoint.job_id,
            "status": checkpoint.status,
            "current_window_start": checkpoint.current_window_start.isoformat(),
            "current_window_end": checkpoint.current_window_end.isoformat(),
            "next_offset": checkpoint.next_offset,
            "pages_processed": pages_processed,
            "papers_fetched": checkpoint.papers_fetched,
            "papers_stored": checkpoint.papers_stored,
            "last_error": checkpoint.last_error,
        }


def main(argv: Optional[list[str]] = None) -> int:
    """CLI for a manually initiated, bounded metadata backfill."""
    import argparse
    import asyncio

    from src.db.factory import make_database
    from src.services.arxiv.factory import make_arxiv_client

    settings = get_settings()
    parser = argparse.ArgumentParser(description="Run a bounded metadata-only arXiv historical backfill")
    parser.add_argument("--job-id", required=True, help="Stable ID; use a new ID to start a different job")
    parser.add_argument("--start-date", required=True, help="Inclusive submitted date, YYYYMMDD")
    parser.add_argument("--end-date", required=True, help="Inclusive submitted date, YYYYMMDD")
    parser.add_argument("--categories", help="Comma-separated category override; defaults to ARXIV settings")
    parser.add_argument("--window-days", type=int, default=7)
    parser.add_argument("--page-size", type=int, default=100)
    parser.add_argument("--max-pages", type=int, default=5, help="Maximum sequential API pages this invocation")
    args = parser.parse_args(argv)
    categories = [item.strip() for item in args.categories.split(",") if item.strip()] if args.categories else None

    database = None
    try:
        database = make_database(settings)
        service = HistoricalMetadataBackfillService(make_arxiv_client(), database)
        summary = asyncio.run(
            service.run(
                job_id=args.job_id,
                start_date=args.start_date,
                end_date=args.end_date,
                categories=categories,
                window_days=args.window_days,
                page_size=args.page_size,
                max_pages=args.max_pages,
            )
        )
        print(summary)
        return 0
    except Exception as exc:
        logger.error("Historical metadata backfill failed (%s)", type(exc).__name__)
        return 1
    finally:
        if database is not None:
            database.teardown()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    raise SystemExit(main())
