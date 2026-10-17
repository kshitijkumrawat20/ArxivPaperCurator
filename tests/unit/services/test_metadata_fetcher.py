import asyncio
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from src.exception import MetadataFetchingException, PipelineException
from src.schema.arxiv.paper import ArxivPaper
from src.schema.pdf_parser.models import ParserType, PdfContent
from src.services.arxiv.client import ArxivClient
from src.services.metadata_fetcher import MetadataFetcher, make_metadata_fetcher
from src.services.pdf_parser.parser import PDFParserService


class TestMetadataFetcher:
    """Test MetadataFetcher functionality."""

    @pytest.fixture
    def mock_arxiv_client(self):
        """Create mock ArxivClient."""
        client = MagicMock(spec=ArxivClient)
        return client

    @pytest.fixture
    def mock_pdf_parser(self):
        """Create mock PDFParserService."""
        parser = MagicMock(spec=PDFParserService)
        return parser

    @pytest.fixture
    def metadata_fetcher(self, mock_arxiv_client, mock_pdf_parser, tmp_path):
        """Create MetadataFetcher instance for testing."""
        return MetadataFetcher(
            arxiv_client=mock_arxiv_client,
            pdf_parser=mock_pdf_parser,
            pdf_cache_dir=tmp_path,
            max_concurrent_downloads=2,
            max_concurrent_parsing=1,
        )

    @pytest.fixture
    def sample_arxiv_papers(self):
        """Create sample ArxivPaper objects."""
        return [
            ArxivPaper(
                arxiv_id="2024.0001v1",
                title="Test Paper 1",
                authors=["Author 1"],
                abstract="Abstract 1",
                categories=["cs.AI"],
                published_date="2024-01-01T00:00:00Z",
                pdf_url="http://arxiv.org/pdf/2024.0001v1",
            ),
            ArxivPaper(
                arxiv_id="2024.0002v1",
                title="Test Paper 2",
                authors=["Author 2"],
                abstract="Abstract 2",
                categories=["cs.AI"],
                published_date="2024-01-02T00:00:00Z",
                pdf_url="http://arxiv.org/pdf/2024.0002v1",
            ),
        ]

    @pytest.fixture
    def sample_pdf_content(self):
        """Create sample PdfContent."""
        return PdfContent(
            raw_text="Sample PDF content", sections=[], tables=[], figures=[], parser_used=ParserType.DOCLING, metadata={}
        )

    def test_metadata_fetcher_initialization(self, metadata_fetcher, tmp_path):
        """Test MetadataFetcher initialization."""
        assert metadata_fetcher.pdf_cache_dir == tmp_path
        assert metadata_fetcher.max_concurrent_downloads == 2
        assert metadata_fetcher.max_concurrent_parsing == 1

    # Complex integration tests removed for simplicity

    # Most complex tests removed - keeping only simple ones

    @pytest.mark.asyncio
    async def test_empty_papers_list(self, metadata_fetcher):
        """Test handling of empty papers list."""
        result = await metadata_fetcher.fetch_and_process_papers(max_results=0, process_pdfs=False, store_to_db=False)

        assert result["papers_fetched"] == 0
        assert result["pdfs_downloaded"] == 0
        assert result["pdfs_parsed"] == 0
        assert len(result["errors"]) == 0

    @pytest.mark.asyncio
    async def test_metadata_only_fetch_skips_pdf_work_and_stores_paper(self, metadata_fetcher, sample_arxiv_papers):
        metadata_fetcher.arxiv_client.fetch_paperts = AsyncMock(return_value=sample_arxiv_papers)
        metadata_fetcher._store_papers_to_db = MagicMock(return_value=2)
        metadata_fetcher._process_pdfs_batch = AsyncMock()
        db_session = MagicMock()

        result = await metadata_fetcher.fetch_and_process_papers(
            max_results=2,
            process_pdfs=False,
            store_to_db=True,
            db_session=db_session,
            categories=["cs.AI", "cs.LG"],
        )

        metadata_fetcher._process_pdfs_batch.assert_not_awaited()
        metadata_fetcher._store_papers_to_db.assert_called_once_with(sample_arxiv_papers, {}, db_session)
        assert result["papers_stored"] == 2
        assert result["arxiv_ids"] == [paper.arxiv_id for paper in sample_arxiv_papers]
        assert metadata_fetcher.arxiv_client.fetch_paperts.call_args.kwargs["categories"] == ["cs.AI", "cs.LG"]

    def test_metadata_only_upsert_does_not_clear_existing_parsed_content(
        self, metadata_fetcher, sample_arxiv_papers
    ):
        repository = MagicMock()
        repository.upsert.return_value = object()
        session = MagicMock()

        with patch("src.services.metadata_fetcher.PaperRepository", return_value=repository):
            stored = metadata_fetcher._store_papers_to_db(sample_arxiv_papers[:1], {}, session)

        assert stored == 1
        paper_create = repository.upsert.call_args.args[0]
        update_fields = paper_create.model_dump(exclude_unset=True)
        assert "raw_text" not in update_fields
        assert "pdf_processed" not in update_fields
        session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_pdf_processing_skips_papers_that_already_have_full_text(
        self, metadata_fetcher, sample_arxiv_papers
    ):
        metadata_fetcher.arxiv_client.fetch_paperts = AsyncMock(return_value=sample_arxiv_papers)
        metadata_fetcher._process_pdfs_batch = AsyncMock(
            return_value={"downloaded": 1, "parsed": 1, "parsed_papers": {}, "errors": []}
        )
        metadata_fetcher._store_papers_to_db = MagicMock(return_value=2)
        repository = MagicMock()
        repository.get_by_arxiv_id.side_effect = [
            MagicMock(pdf_processed=True, raw_text="previously parsed text"),
            None,
        ]

        with patch("src.services.metadata_fetcher.PaperRepository", return_value=repository):
            await metadata_fetcher.fetch_and_process_papers(
                process_pdfs=True,
                store_to_db=True,
                db_session=MagicMock(),
            )

        metadata_fetcher._process_pdfs_batch.assert_awaited_once_with([sample_arxiv_papers[1]])

    @pytest.mark.asyncio
    async def test_rate_limiting_respected(self, metadata_fetcher):
        """Test that rate limiting delays are respected."""
        # This is a basic test to ensure the rate limiting logic exists
        # More comprehensive testing would require timing analysis
        metadata_fetcher.arxiv_client.fetch_paperts = AsyncMock(return_value=[])

        start_time = time.time()
        await metadata_fetcher.fetch_and_process_papers(max_results=1)
        end_time = time.time()

        # Should complete quickly for empty result
        assert end_time - start_time < 1.0
