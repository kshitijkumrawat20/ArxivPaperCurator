from datetime import date

from fastapi import APIRouter, Depends , HTTPException, Path, Query
from sqlalchemy.orm import Session
from src.dependencies import CacheDep, EmbeddingsDep, LangfuseDep, OllamaDep, OpenSearchDep, SessionDep
from src.schema.api.ask import PaperAskRequest, PaperAskResponse
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
