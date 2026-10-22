from datetime import date

from fastapi import APIRouter, Depends , HTTPException, Path, Query
from sqlalchemy.orm import Session
from src.dependencies import (
    ArxivDep, CacheDep, EmbeddingsDep, LangfuseDep, OllamaDep, OpenSearchDep,
    PDFParserDep, SessionDep, SettingsDep,
)
from src.schema.api.ask import PaperAskRequest, PaperAskResponse
from src.schema.api.deep_dive import PaperDeepDiveRequest, PaperDeepDiveResponse, PaperPreparationResponse
from src.schema.api.project_match import ProjectMatchRequest, ProjectMatchResponse
from src.schema.arxiv.paper import PaperResponse, PaperSearchResponse
from src.schema.api.search import MetadataDiscoveryResponse
from src.respositories.paper import PaperRepository 
from src.services.metadata_discovery import MetadataDiscoveryService
from src.services.paper_scoped_rag import (
    PaperGenerationUnavailableError,
    PaperNotFoundError,
    PaperNotIndexedError,
    PaperScopedRAGService,
    PaperSearchUnavailableError,
)
from src.services.langfuse.tracer import RAGTracer
from src.respositories.paper_brief import PaperBriefRepository
from src.services.indexing.hybrid_indexer import HybridIndexingService
from src.services.indexing.text_chunker import TextChunker
from src.services.paper_preparation import (
    PaperPreparationDownloadError,
    PaperPreparationIndexingError,
    PaperPreparationNotFoundError,
    PaperPreparationParsingError,
    PaperPreparationService,
    PaperPreparationStorageError,
)
from src.services.paper_deep_dive import (
    PaperDeepDiveGenerationUnavailableError,
    PaperDeepDiveInsufficientEvidenceError,
    PaperDeepDiveNotFoundError,
    PaperDeepDiveNotPreparedError,
    PaperDeepDivePersistenceError,
    PaperDeepDiveSearchUnavailableError,
    PaperDeepDiveService,
)
from src.services.project_paper_match import ProjectMatchSearchUnavailableError, ProjectPaperMatchService

router = APIRouter(prefix = "/papers", tags=["Papers"])
@router.get("/", response_model=PaperSearchResponse)
def list_paper(
    db: SessionDep, 
    limit: int = Query(default=100, ge=1, le=100, description="Number of papers to return (default: 100, max: 1000)"),
    offset: int = Query(default=0, ge=0, description="Number of papers to skip (default: 0)"),
) -> PaperSearchResponse: 
    """Get a list of Papers with pagination"""
    paper_repo = PaperRepository(db)
    papers = paper_repo.get_all(limit=limit, offset=offset)
    total_count = paper_repo.get_count()
    return PaperSearchResponse(papers=[PaperResponse.model_validate(paper) for paper in papers], total=total_count)


@router.get("/discover", response_model=MetadataDiscoveryResponse)
def discover_papers(
    opensearch: OpenSearchDep,
    query: str = Query(default="", max_length=500),
    categories: list[str] | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    size: int = Query(default=10, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> MetadataDiscoveryResponse:
    """Search paper-level metadata with BM25; empty query lists newest papers."""
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="date_from must be on or before date_to")
    try:
        result = MetadataDiscoveryService(opensearch).search(
            query=query, size=size, from_=offset, categories=categories, date_from=date_from, date_to=date_to
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Paper discovery search is currently unavailable") from exc
    return MetadataDiscoveryResponse(
        query=query,
        total=result["total"],
        size=size,
        **{"from": offset},
        papers=result["hits"],
    )


@router.post("/match-project", response_model=ProjectMatchResponse)
def match_project_to_papers(
    request: ProjectMatchRequest,
    opensearch: OpenSearchDep,
) -> ProjectMatchResponse:
    """Rank papers from the vector-free metadata index for a project description."""
    try:
        return ProjectPaperMatchService(opensearch).match(request)
    except ProjectMatchSearchUnavailableError as exc:
        # Don't expose internal OpenSearch details or fall back to global chunk search.
        raise HTTPException(
            status_code=503,
            detail="Project matching is temporarily unavailable because metadata search failed.",
        ) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Project matching is temporarily unavailable.") from exc


@router.post("/{arxiv_id}/prepare", response_model=PaperPreparationResponse)
async def prepare_paper(
    arxiv_id: str,
    db: SessionDep,
    arxiv: ArxivDep,
    pdf_parser: PDFParserDep,
    embeddings: EmbeddingsDep,
    opensearch: OpenSearchDep,
    settings: SettingsDep,
) -> PaperPreparationResponse:
    """Download/parse/index only the selected exact paper version, on demand."""
    chunker = TextChunker(
        chunk_size=settings.chunking.chunk_size,
        overlap_size=settings.chunking.overlap_size,
        min_chunk_size=settings.chunking.min_chunk_size,
    )
    indexer = HybridIndexingService(chunker, embeddings, opensearch)
    service = PaperPreparationService(
        PaperRepository(db), arxiv, pdf_parser, indexer, opensearch, settings=settings
    )
    try:
        return PaperPreparationResponse(**(await service.prepare(arxiv_id)))
    except PaperPreparationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Paper {arxiv_id!r} was not found") from exc
    except PaperPreparationDownloadError as exc:
        raise HTTPException(status_code=502, detail={"code": "pdf_download_failed", "message": str(exc)}) from exc
    except PaperPreparationParsingError as exc:
        raise HTTPException(status_code=422, detail={"code": "pdf_parsing_failed", "message": str(exc)}) from exc
    except PaperPreparationStorageError as exc:
        raise HTTPException(status_code=503, detail={"code": "parsed_content_not_saved", "message": str(exc)}) from exc
    except PaperPreparationIndexingError as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "parsed_not_indexed",
                "message": str(exc),
                "parsed_content_saved": exc.parsed_saved,
                "retry": "Repeat this request to retry indexing saved parsed content; PDF parsing will be skipped.",
                "indexing_stats": exc.stats,
            },
        ) from exc


@router.post("/{arxiv_id}/deep-dive", response_model=PaperDeepDiveResponse)
async def paper_deep_dive(
    arxiv_id: str,
    request: PaperDeepDiveRequest,
    db: SessionDep,
    opensearch: OpenSearchDep,
    embeddings: EmbeddingsDep,
    ollama: OllamaDep,
    settings: SettingsDep,
) -> PaperDeepDiveResponse:
    """Generate/reuse a validated brief from this paper's retrieved full-text chunks only."""
    service = PaperDeepDiveService(
        paper_repository=PaperRepository(db),
        brief_repository=PaperBriefRepository(db),
        opensearch_client=opensearch,
        embeddings_service=embeddings,
        ollama_client=ollama,
        settings=settings,
    )
    try:
        return await service.generate(arxiv_id, request)
    except PaperDeepDiveNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Paper {arxiv_id!r} was not found") from exc
    except PaperDeepDiveNotPreparedError as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "paper_not_prepared", "message": "Prepare this paper's full text before requesting a Deep Dive."},
        ) from exc
    except PaperDeepDiveInsufficientEvidenceError as exc:
        raise HTTPException(status_code=422, detail={"code": "insufficient_evidence", "message": str(exc)}) from exc
    except PaperDeepDiveSearchUnavailableError as exc:
        raise HTTPException(status_code=503, detail={"code": "paper_search_unavailable", "message": str(exc)}) from exc
    except PaperDeepDiveGenerationUnavailableError as exc:
        raise HTTPException(status_code=503, detail={"code": "generation_unavailable", "message": str(exc)}) from exc
    except PaperDeepDivePersistenceError as exc:
        raise HTTPException(status_code=503, detail={"code": "brief_persistence_unavailable", "message": str(exc)}) from exc


@router.post("/{arxiv_id}/ask", response_model=PaperAskResponse)
async def ask_about_paper(
    request: PaperAskRequest,
    arxiv_id: str,
    db: SessionDep,
    opensearch: OpenSearchDep,
    embeddings: EmbeddingsDep,
    ollama: OllamaDep,
    langfuse: LangfuseDep,
    cache: CacheDep,
) -> PaperAskResponse:
    """Answer using evidence retrieved only from the exact selected paper ID."""
    try:
        service = PaperScopedRAGService(
            paper_repository=PaperRepository(db),
            opensearch_client=opensearch,
            embeddings_service=embeddings,
            ollama_client=ollama,
            rag_tracer=RAGTracer(langfuse),
            cache_client=cache,
        )
        return await service.ask(arxiv_id, request)
    except PaperNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Paper {arxiv_id!r} was not found") from exc
    except PaperNotIndexedError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "full_text_not_indexed",
                "message": "This paper exists as metadata, but its full text is not indexed. Full-text processing is required.",
            },
        ) from exc
    except (PaperSearchUnavailableError, PaperGenerationUnavailableError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Paper question-answering service is unavailable") from exc


@router.get("/{arxiv_id}", response_model=PaperResponse)
def get_paper_details(
    db : SessionDep, 
    arxiv_id: str = Path(
        ..., description="The arXiv ID of the paper to retrieve details for", examples=["2101.00001"]
    )
) -> PaperResponse: 
    """Get details of paper by arXiv ID."""
    paper_repo = PaperRepository(db)
    paper=  paper_repo.get_by_arxiv_id(arxiv_id)
    if not paper: 
        raise HTTPException(status_code=404, detail=f"Paper with arXiv ID {arxiv_id} not found.")
    return PaperResponse.model_validate(paper)
