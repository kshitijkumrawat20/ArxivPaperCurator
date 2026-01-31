from typing import List
from pydantic import BaseModel, Field

class AskRequest(BaseModel):
    """Request schema for asking question about the papers ."""
    questions: List[str] = Field(..., description="List of questions to ask about the papers.")

class Papersource(BaseModel):
    """Schema for paper source information  in responses."""
    arxiv_id : str = Field(..., description="The unique identifier for the arXiv paper.")
    title: str = Field(..., description="The title of the arXiv paper.")
    author: List[str] = Field(..., description="List of authors of the arXiv paper.")
    abstract_preview: str = Field(..., description="The abstract of the arXiv paper."
                                  )
    
class AskResponse(BaseModel):
    """Response schema for answers to questions about the papers."""
    answer: str = Field(..., description="The answer to the question based on the papers.")
    sources: List[Papersource] = Field(..., description="List of paper sources used to generate the answer.")