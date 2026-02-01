from fastapi import APIRouter, Depends, HTTPException, Path
from src.schemas.arxiv.paper import PaperResponse
from src.dependencies import SettingDep
from sqlalchemy.orm import Session 
from src.repositories.paper import PaperRepository

router = APIRouter(prefix="/papers", tags=["papers"])

@router.get("/{paper_id}", response_model = PaperResponse)
def get_paper_details(
    db: Session, 
    paper_id: str = Path(
        ..., description="arXiv paper ID (e.g., '2401.00001' or '2401.00001v1')", regex=r"^\d{4}\.\d{4,5}(v\d+)?$"
    ),
) -> PaperResponse:
    """Get details of a specific arXiv paper by its ID."""
    paper_repo = PaperRepository(db)
    paper = paper_repo.get_by_arxiv_id(paper_id)

    if not paper: 
        raise HTTPException(status_code=404, detail="Paper not found")
    
    return PaperResponse.model_validate(paper)

