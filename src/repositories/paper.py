from typing import List , Optional
from uuid import UUID
from sqlalchemy import select
from sympy import limit
from src.models.paper import Paper
from src.schemas.arxiv.paper import PaperCreate
from sqlalchemy.orm import Session


class PaperRepository:
    def __init__(self, session: Session):
        self.session = session
    
    def create(self, paper: PaperCreate) -> Paper:
        db_paper = Paper(**paper.model_dump()) 
        self.session.add(db_paper)
        self.session.commit()
        self.session.refresh(db_paper)
        return db_paper
    
    def get_by_arxiv_id(self, arxiv_id: str) -> Optional[Paper]:
        return self.session.query(Paper).filter(Paper.arxiv_id == arxiv_id).first() 
    
    def get_paper_by_id(self, paper_id: UUID) -> Optional[Paper]:
        return self.session.query(Paper).filter(Paper.id == paper_id).first()
    
    def get_all(self, limit: int = 100, offset: int = 0) -> List[Paper]:
        return self.session.query(Paper).order_by(Paper.published_date.desc()).limit(limit).offset(offset).all()
        