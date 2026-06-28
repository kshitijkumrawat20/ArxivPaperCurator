from fastapi import APIRouter, Depends , HTTPException, Path
from sqlalchemy.orm import Session
from src.dependencies import SessionDep
from src.schema.paper import PaperResponse
from src.respositories.paper import PaperRepository 

router = APIRouter(prefix = "/papers", tags=["Papers"])

@router.get("/{arxiv_id}", response_model=PaperResponse)
def get_paper_details(
    db : SessionDep, 
    arxiv_id: str = Path(
        ..., description="The arXiv ID of the paper to retrieve details for", example="2101.00001"
    )
) -> PaperResponse: 
    """Get details of paper by arXiv ID."""
    paper_repo = PaperRepository(db)
    paper=  paper_repo.get_by_arxiv_id(arxiv_id)
    if not paper: 
        raise HTTPException(status_code=404, detail=f"Paper with arXiv ID {arxiv_id} not found.")
    return PaperResponse.model_validate(paper)
