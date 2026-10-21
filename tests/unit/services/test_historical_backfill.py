import asyncio
from contextlib import contextmanager
from copy import deepcopy
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.models.historical_backfill import HistoricalBackfillCheckpoint
from src.schema.arxiv.paper import ArxivPaper
from src.services.historical_backfill import HistoricalMetadataBackfillService


class MemoryDatabase:
    def __init__(self):
        self.checkpoints = {}
        self.papers = {}
        self.fail_on_arxiv_id = None

    @contextmanager
    def get_session(self):
        yield object()


class MemoryCheckpointRepository:
    def __init__(self, session, database):
        self.database = database

    def get(self, job_id):
        checkpoint = self.database.checkpoints.get(job_id)
        return deepcopy(checkpoint) if checkpoint else None

    def create(self, checkpoint):
        self.database.checkpoints[checkpoint.job_id] = deepcopy(checkpoint)
        return deepcopy(checkpoint)

    def save(self, checkpoint):
        self.database.checkpoints[checkpoint.job_id] = deepcopy(checkpoint)
        return deepcopy(checkpoint)


class MemoryPaperRepository:
    def __init__(self, session, database):
        self.database = database

    def upsert(self, paper):
        if paper.arxiv_id == self.database.fail_on_arxiv_id:
            raise RuntimeError("mock persistence failure")
        self.database.papers[paper.arxiv_id] = paper
        return SimpleNamespace(arxiv_id=paper.arxiv_id)


@pytest.fixture
def backfill():
    database = MemoryDatabase()
    arxiv = MagicMock()
    arxiv.search_categories = ["cs.AI", "cs.LG"]
    service = HistoricalMetadataBackfillService(
        arxiv_client=arxiv,
        database=database,
        paper_repository_factory=lambda session: MemoryPaperRepository(session, database),
        checkpoint_repository_factory=lambda session: MemoryCheckpointRepository(session, database),
    )
    return service, arxiv, database


def paper(arxiv_id):
    return ArxivPaper(
        arxiv_id=arxiv_id,
        title=f"Paper {arxiv_id}",
        authors=["A. Author"],
        abstract="Short metadata abstract",
        categories=["cs.AI"],
        published_date="2020-01-01T00:00:00Z",
        pdf_url=f"https://arxiv.org/pdf/{arxiv_id}",
    )


def run(service, **kwargs):
    options = {
        "job_id": "test-backfill",
        "start_date": "20200101",
        "end_date": "20200110",
        "categories": ["cs.AI"],
        "window_days": 5,
        "page_size": 2,
        "max_pages": 5,
    }
    options.update(kwargs)
    return asyncio.run(service.run(**options))


def test_paginates_sequentially_and_stops_at_execution_page_limit(backfill):
    service, arxiv, database = backfill
    arxiv.fetch_paperts = AsyncMock(side_effect=[[paper("2001.00001"), paper("2001.00002")]] * 2)

    result = run(service, max_pages=2)

    assert result["status"] == "paused"
    assert result["pages_processed"] == 2
    assert result["next_offset"] == 4
    assert result["papers_stored"] == 4
    assert [call.kwargs["start"] for call in arxiv.fetch_paperts.await_args_list] == [0, 2]
    assert all(call.kwargs["categories"] == ["cs.AI"] for call in arxiv.fetch_paperts.await_args_list)
    assert len(database.papers) == 2  # repeated IDs are upserted, not duplicated
    assert all("raw_text" not in value.model_dump(exclude_unset=True) for value in database.papers.values())
    assert not hasattr(service, "pdf_parser")
    assert not hasattr(service, "embeddings_client")
    assert not hasattr(service, "opensearch_client")
    assert all("raw_text" not in value.model_dump(exclude_unset=True) for value in database.papers.values())
    assert not hasattr(service, "pdf_parser")
    assert not hasattr(service, "embeddings_client")
    assert not hasattr(service, "opensearch_client")


def test_exhausted_page_advances_to_next_date_window_then_completes(backfill):
    service, arxiv, _ = backfill
    arxiv.fetch_paperts = AsyncMock(side_effect=[[paper("2001.00001")], []])

    result = run(service, window_days=5)

    assert result["status"] == "completed"
    assert result["pages_processed"] == 2
    first_call, second_call = arxiv.fetch_paperts.await_args_list
    assert (first_call.kwargs["from_date"], first_call.kwargs["to_date"]) == ("20200101", "20200105")
    assert (second_call.kwargs["from_date"], second_call.kwargs["to_date"]) == ("20200106", "20200110")


def test_resume_uses_saved_offset(backfill):
    service, arxiv, database = backfill
    database.checkpoints["test-backfill"] = HistoricalBackfillCheckpoint(
        job_id="test-backfill",
        start_date=date(2020, 1, 1),
        end_date=date(2020, 1, 10),
        categories=["cs.AI"],
        window_days=5,
        page_size=2,
        current_window_start=date(2020, 1, 1),
        current_window_end=date(2020, 1, 5),
        next_offset=6,
        status="paused",
        papers_fetched=6,
        papers_stored=6,
        updated_at=datetime.now(timezone.utc),
    )
    arxiv.fetch_paperts = AsyncMock(return_value=[paper("2001.00007")])

    result = run(service, max_pages=1)

    assert arxiv.fetch_paperts.await_args.kwargs["start"] == 6
    assert result["status"] == "paused"
    assert result["papers_stored"] == 7


def test_failed_page_write_does_not_advance_checkpoint_and_replay_is_idempotent(backfill):
    service, arxiv, database = backfill
    page = [paper("2001.00001"), paper("2001.00002")]
    arxiv.fetch_paperts = AsyncMock(return_value=page)
    database.fail_on_arxiv_id = "2001.00002"

    with pytest.raises(RuntimeError, match="mock persistence failure"):
        run(service, max_pages=1)

    checkpoint = database.checkpoints["test-backfill"]
    assert checkpoint.status == "failed"
    assert checkpoint.next_offset == 0
    assert checkpoint.papers_fetched == 0
    assert checkpoint.papers_stored == 0

    database.fail_on_arxiv_id = None
    result = run(service, max_pages=1)

    assert arxiv.fetch_paperts.await_args_list[-1].kwargs["start"] == 0
    assert result["papers_stored"] == 2
    assert set(database.papers) == {p.arxiv_id for p in page}


def test_empty_page_completes_window_and_pdfs_embeddings_search_are_not_wired(backfill):
    service, arxiv, database = backfill
    arxiv.fetch_paperts = AsyncMock(return_value=[])

    result = run(service, end_date="20200101", window_days=1, page_size=5)

    assert result["status"] == "completed"
    assert result["pages_processed"] == 1
    assert result["papers_stored"] == 0
    assert database.papers == {}
    assert not hasattr(service, "pdf_parser")
    assert not hasattr(service, "embeddings_client")
    assert not hasattr(service, "opensearch_client")


def test_incompatible_resume_parameters_are_rejected_without_mutating_checkpoint(backfill):
    service, arxiv, database = backfill
    arxiv.fetch_paperts = AsyncMock(return_value=[])
    run(service, max_pages=1)
    checkpoint_before = deepcopy(database.checkpoints["test-backfill"])

    with pytest.raises(ValueError, match="choose a new job ID"):
        run(service, categories=["cs.LG"], max_pages=1)

    checkpoint_after = database.checkpoints["test-backfill"]
    assert checkpoint_after.status == checkpoint_before.status
    assert checkpoint_after.categories == checkpoint_before.categories
    assert checkpoint_after.next_offset == checkpoint_before.next_offset
    arxiv.fetch_paperts.assert_awaited_once()
