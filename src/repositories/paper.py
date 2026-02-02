from typing import List , Optional
from uuid import UUID
from sqlalchemy import select
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
        
    def update(self, paper: Paper) -> Paper: 
        self.session.add(paper) # re-add to session to mark as dirty
        self.session.commit() 
        self.session.refresh(paper) # refresh to get updated fields
        return paper
    
    def upsert(self, paper_create: PaperCreate) -> Paper:
        # Check if the paper already exists by arxiv_id
        exisiting_paper = self.get_by_arxiv_id(paper_create.arxive_id)
        if exisiting_paper:
            # Update the existing paper
            for key, value in paper_create.model_dump(exclude_unset=True).items():
                setattr(exisiting_paper, key, value)
            return self.update(exisiting_paper)
        else:
            # Create a new paper
            return self.create(paper_create)