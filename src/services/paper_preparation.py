"""On-demand, single-paper PDF preparation and indexing."""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from src.config import Settings, get_settings
from src.respositories.paper import PaperRepository
from src.schema.pdf_parser.models import ArxivMetadata, ParsedPaper
from src.services.arxiv.client import ArxivClient
from src.services.parsed_content import serialize_parsed_content

if TYPE_CHECKING:
    from src.services.indexing.hybrid_indexer import HybridIndexingService
    from src.services.opensearch.client import OpenSearchClient
    from src.services.pdf_parser.parser import PDFParserService

class PaperPreparationNotFoundError(Exception):
    pass


class PaperPreparationDownloadError(Exception):
    pass


class PaperPreparationParsingError(Exception):
    pass


class PaperPreparationStorageError(Exception):
    pass


class PaperPreparationIndexingError(Exception):
    def __init__(self, message: str, *, parsed_saved: bool, stats: dict[str, int] | None = None):
        super().__init__(message)
        self.parsed_saved = parsed_saved
        self.stats = stats or {}


class PaperPreparationService:
    """Prepare and index only the requested exact arXiv paper/version."""

    def __init__(
        self,
        paper_repository: PaperRepository,
        arxiv_client: ArxivClient,
        pdf_parser: PDFParserService,
        indexing_service: HybridIndexingService,
        opensearch_client: OpenSearchClient,
        settings: Settings | None = None,
    ):
        self.paper_repository = paper_repository
        self.arxiv_client = arxiv_client
        self.pdf_parser = pdf_parser
        self.indexing_service = indexing_service
        self.opensearch_client = opensearch_client
        self.settings = settings or get_settings()

    async def prepare(self, arxiv_id: str) -> dict[str, Any]:
        paper = self.paper_repository.get_by_arxiv_id(arxiv_id)
        if paper is None:
            raise PaperPreparationNotFoundError(arxiv_id)

        try:
            existing_chunks = self.opensearch_client.get_chunks_by_paper(
                arxiv_id, limit=1, raise_errors=True
            )
        except Exception as exc:
            raise PaperPreparationIndexingError(
                "Could not check existing paper chunks", parsed_saved=bool(paper.raw_text)
            ) from exc

        full_text_available = bool((paper.raw_text or "").strip())
        if full_text_available and existing_chunks:
            return self._result(arxiv_id, "ready", True, True, 0, reused=True)

        if not full_text_available:
            try:
                pdf_path = await self.arxiv_client.download_paper_pdf(
                    arxiv_id,
                    max_file_size_bytes=self.settings.pdf_parser.max_file_size_mb * 1024 * 1024,
                )
            except Exception as exc:
                raise PaperPreparationDownloadError("PDF download failed") from exc
            if not pdf_path:
                raise PaperPreparationDownloadError("PDF download failed")

            try:
                pdf_content = await self.pdf_parser.parse_pdf(pdf_path)
                if not pdf_content or not (pdf_content.raw_text or "").strip():
                    raise ValueError("Parser returned no extracted text")
            except Exception as exc:
                raise PaperPreparationParsingError("PDF parsing failed") from exc

            published_date = paper.published_date
            if isinstance(published_date, (datetime, date)):
                published_date = published_date.isoformat()
            parsed = ParsedPaper(
                arxiv_metadata=ArxivMetadata(
                    title=paper.title,
                    authors=paper.authors or [],
                    abstract=paper.abstract or "",
                    arxiv_id=arxiv_id,
                    categories=paper.categories or [],
                    published_date=str(published_date or ""),
                    pdf_url=paper.pdf_url or "",
                ),
                pdf_content=pdf_content,
            )
            serialized = serialize_parsed_content(parsed)
            if not serialized.get("pdf_processed") or not serialized.get("raw_text"):
                raise PaperPreparationParsingError("Parsed content could not be serialized")

            for key, value in serialized.items():
                setattr(paper, key, value)
            try:
                paper = self.paper_repository.update(paper)
            except Exception as exc:
                raise PaperPreparationStorageError("Parsed content could not be persisted") from exc

        try:
            # Clear only this paper's possibly partial old index before retrying;
            # strict errors prevent adding duplicate chunks after a failed attempt.
            if existing_chunks:
                self.opensearch_client.delete_paper_chunks(arxiv_id, raise_errors=True)
            stats = await self.indexing_service.index_paper(self._paper_data(paper))
            if stats.get("error", 0) or stats.get("chunks_indexed", 0) < 1:
                raise RuntimeError(f"Indexing returned incomplete result: {stats}")
            verified = self.opensearch_client.get_chunks_by_paper(
                arxiv_id, limit=1, raise_errors=True
            )
            if not verified:
                raise RuntimeError("No paper chunks found after indexing")
        except Exception as exc:
            stats = locals().get("stats", {})
            raise PaperPreparationIndexingError(
                "Paper text was saved, but full-text indexing did not complete; retry to index the saved text.",
                parsed_saved=True,
                stats=stats,
            ) from exc

        return self._result(
            arxiv_id, "ready", True, True, stats.get("chunks_indexed", 0), reused=full_text_available
        )

    @staticmethod
    def _paper_data(paper: Any) -> dict[str, Any]:
        return {
            "id": str(paper.id),
            "arxiv_id": paper.arxiv_id,
            "title": paper.title,
            "authors": paper.authors or [],
            "abstract": paper.abstract or "",
            "categories": paper.categories or [],
            "published_date": paper.published_date.isoformat() if hasattr(paper.published_date, "isoformat") else paper.published_date,
            "pdf_url": paper.pdf_url,
            "raw_text": paper.raw_text,
            "sections": paper.sections or [],
        }

    @staticmethod
    def _result(arxiv_id: str, status: str, parsed: bool, indexed: bool, chunks: int, *, reused: bool) -> dict[str, Any]:
        return {
            "arxiv_id": arxiv_id,
            "status": status,
            "parsed": parsed,
            "indexed": indexed,
            "chunks_indexed": chunks,
            "reused_existing_content": reused,
        }
