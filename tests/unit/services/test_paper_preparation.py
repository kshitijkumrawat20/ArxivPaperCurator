from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.schema.pdf_parser.models import ParserType, PaperSection, PdfContent
from src.services.arxiv.client import ArxivClient
from src.services.paper_preparation import (
    PaperPreparationIndexingError,
    PaperPreparationNotFoundError,
    PaperPreparationParsingError,
    PaperPreparationService,
)


ARXIV_ID = "1706.03762v7"


@pytest.mark.asyncio
async def test_exact_pdf_download_keeps_version_and_reuses_configured_download_path(tmp_path):
    client = ArxivClient(SimpleNamespace(
        pdf_cache_dir=str(tmp_path), namespaces={}, base_url="https://export.arxiv.org/api/query",
        rate_limit_delay=0, timeout_seconds=3, max_results=1, search_category="cs.AI",
        search_categories=None, download_max_retries=2, download_retry_delay=0,
    ))
    client._download_with_retry = AsyncMock(return_value=True)

    path = await client.download_paper_pdf(ARXIV_ID, max_file_size_bytes=1024)

    assert path.name == f"{ARXIV_ID}.pdf"
    client._download_with_retry.assert_awaited_once_with(
        f"https://arxiv.org/pdf/{ARXIV_ID}.pdf", path, max_file_size_bytes=1024
    )


def paper(*, raw_text=None):
    return SimpleNamespace(
        id="paper-row-id", arxiv_id=ARXIV_ID, title="Attention Paper", authors=["A Author"],
        abstract="An abstract.", categories=["cs.CL"], published_date=datetime(2017, 6, 12, tzinfo=timezone.utc),
        pdf_url=f"https://arxiv.org/pdf/{ARXIV_ID}.pdf", raw_text=raw_text,
        sections=None, references=None, parser_used=None, parser_metadata=None,
        pdf_processed=False, pdf_processing_date=None,
    )


def parsed_content():
    return PdfContent(
        raw_text="Full extracted paper text.",
        sections=[PaperSection(title="Method", content="The method is attention.", level=1)],
        references=["Example citation"], parser_used=ParserType.DOCLING, metadata={"source": "docling"},
    )


def service_setup(*, raw_text=None, index_stats=None, initial_chunks=None):
    stored_paper = paper(raw_text=raw_text)
    repository = MagicMock()
    repository.get_by_arxiv_id.return_value = stored_paper
    repository.update.side_effect = lambda value: value
    arxiv = MagicMock()
    arxiv.pdf_cache_dir = Path(".")
    arxiv.download_paper_pdf = AsyncMock(return_value=Path("selected-version.pdf"))
    parser = MagicMock()
    parser.parse_pdf = AsyncMock(return_value=parsed_content())
    indexer = MagicMock()
    indexer.index_paper = AsyncMock(return_value=index_stats or {"chunks_created": 1, "chunks_indexed": 1, "error": 0})
    opensearch = MagicMock()
    opensearch.get_chunks_by_paper.side_effect = [initial_chunks or [] , [{"chunk_id": "chunk-1"}]]
    settings = SimpleNamespace(pdf_parser=SimpleNamespace(max_file_size_mb=50))
    service = PaperPreparationService(repository, arxiv, parser, indexer, opensearch, settings)
    return service, stored_paper, repository, arxiv, parser, indexer, opensearch


@pytest.mark.asyncio
async def test_already_prepared_paper_reuses_existing_text_and_chunks():
    service, _, _, arxiv, parser, indexer, _ = service_setup(
        raw_text="Already parsed", initial_chunks=[{"chunk_id": "existing"}]
    )

    result = await service.prepare(ARXIV_ID)

    assert result["status"] == "ready" and result["reused_existing_content"] is True
    arxiv.download_paper_pdf.assert_not_awaited()
    parser.parse_pdf.assert_not_awaited()
    indexer.index_paper.assert_not_awaited()


@pytest.mark.asyncio
async def test_metadata_only_paper_downloads_exact_version_persists_and_indexes():
    service, stored, repository, arxiv, parser, indexer, _ = service_setup()

    result = await service.prepare(ARXIV_ID)

    arxiv.download_paper_pdf.assert_awaited_once_with(ARXIV_ID, max_file_size_bytes=50 * 1024 * 1024)
    parser.parse_pdf.assert_awaited_once_with(Path("selected-version.pdf"))
    assert stored.raw_text == "Full extracted paper text."
    assert stored.sections[0]["title"] == "Method"
    assert stored.references == ["Example citation"]
    assert stored.parser_used == "docling" and stored.pdf_processed is True
    repository.update.assert_called_once_with(stored)
    assert indexer.index_paper.await_args.args[0]["arxiv_id"] == ARXIV_ID
    assert result["indexed"] is True


@pytest.mark.asyncio
async def test_parse_failure_does_not_persist_or_mark_successful():
    service, stored, repository, _, parser, indexer, _ = service_setup()
    parser.parse_pdf.side_effect = RuntimeError("bad pdf")

    with pytest.raises(PaperPreparationParsingError):
        await service.prepare(ARXIV_ID)

    repository.update.assert_not_called()
    assert stored.pdf_processed is False
    indexer.index_paper.assert_not_awaited()


@pytest.mark.asyncio
async def test_index_failure_keeps_parsed_text_and_retry_skips_download_and_parse():
    service, stored, repository, arxiv, parser, indexer, opensearch = service_setup(
        index_stats={"chunks_created": 2, "chunks_indexed": 1, "error": 1}
    )
    opensearch.get_chunks_by_paper.side_effect = [[], [], [{"chunk_id": "chunk-1"}]]
    with pytest.raises(PaperPreparationIndexingError) as exc_info:
        await service.prepare(ARXIV_ID)
    assert exc_info.value.parsed_saved is True
    assert stored.raw_text == "Full extracted paper text."
    assert repository.update.call_count == 1

    indexer.index_paper.return_value = {"chunks_created": 1, "chunks_indexed": 1, "error": 0}
    result = await service.prepare(ARXIV_ID)

    arxiv.download_paper_pdf.assert_awaited_once_with(ARXIV_ID, max_file_size_bytes=50 * 1024 * 1024)
    parser.parse_pdf.assert_awaited_once()
    assert indexer.index_paper.await_count == 2
    assert result["status"] == "ready"


@pytest.mark.asyncio
async def test_missing_paper_is_distinct():
    service, _, repository, _, _, _, _ = service_setup()
    repository.get_by_arxiv_id.return_value = None
    with pytest.raises(PaperPreparationNotFoundError):
        await service.prepare(ARXIV_ID)
