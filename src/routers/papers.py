from fastapi import APIRouter, HTTPException, Path,Query
from src.schemas.arxiv.paper import PaperResponse, PaperSearchResponse
from src.dependencies import DBSessionDep
from sqlalchemy.orm import Session
from src.repositories.paper import PaperRepository

router = APIRouter(prefix="/papers", tags=["papers"])
@router.get("/", response_model=PaperSearchResponse)
def list_papers(
    db: DBSessionDep,
    limit: int = Query(default=10, ge=1, le=100, description="Number of papers to return (1-100)"),
    offset: int = Query(default=0, ge=0, description="Number of papers to skip"),
) -> PaperSearchResponse:
    """Get a list of papers with pagination."""
    paper_repo = PaperRepository(db)
    papers = paper_repo.get_all(limit=limit, offset=offset)

    # Get total count for pagination info
    total = paper_repo.get_count()

    return PaperSearchResponse(papers=[PaperResponse.model_validate(paper) for paper in papers], total=total)

@router.get("/{paper_id}", response_model=PaperResponse)
def get_paper_details(
    paper_id: str = Path(
        ..., description="arXiv paper ID (e.g., '2401.00001' or '2401.00001v1')", pattern=r"^\d{4}\.\d{4,5}(v\d+)?$"
    ),
    db: DBSessionDep = None,
) -> PaperResponse:
    """Get details of a specific arXiv paper by its ID."""
    paper_repo = PaperRepository(db)
    paper = paper_repo.get_by_arxiv_id(paper_id)

    if not paper: 
        raise HTTPException(status_code=404, detail="Paper not found")
    
    return PaperResponse.model_validate(paper)

