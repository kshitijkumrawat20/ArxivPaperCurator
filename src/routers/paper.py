from fastapi import APIRouter, Depends , HTTPException, Path, Query
from sqlalchemy.orm import Session
from src.dependencies import SessionDep
from src.schema.arxiv.paper import PaperResponse, PaperSearchResponse
from src.respositories.paper import PaperRepository 

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
