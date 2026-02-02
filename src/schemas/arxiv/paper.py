from datetime import datetime
from typing import Any, Dict, List, Optional, Union 
from uuid import UUID 
from pydantic import BaseModel, Field 

class ArxivPaper(BaseModel): 
    "Schema representing an arXiv paper."
    arxiv_id: str = Field(..., description="The unique identifier for the arXiv paper.")
    title: str = Field(..., description="The title of the arXiv paper.")
    authors: List[str] = Field(..., description="List of authors of the arXiv paper.")
    abstract: str = Field(..., description="The abstract of the arXiv paper.")
    categories: List[str] = Field(..., description="List of categories the paper belongs to.")
    published_date: str = Field(..., description="The publication date of the arXiv paper.")
    pdf_url: str = Field(..., description="The URL to download the PDF of the arXiv paper.")

class PaperBase(BaseModel):
    # core arxiv metadata 
    arxive_id: str = Field(..., description="The unique identifier for the arXiv paper.")
    title: str = Field(..., description="The title of the arXiv paper.")
    authors: List[str] = Field(..., description="List of authors of the arXiv paper.")
    abstract: str = Field(..., description="The abstract of the arXiv paper.")  
    categories: List[str] = Field(..., description="List of categories the paper belongs to.")
    published_date: datetime = Field(..., description="The publication date of the arXiv paper.")
    pdf_url: str = Field(..., description="The URL to download the PDF of the arXiv paper.")

class PaperCreate(PaperBase):
    """Schema for creating a paper with optional parsed content."""
    # parsed content (optional - added when PDF is processed)
    raw_text: Optional[str] = Field(None, description="The raw text content of the paper.")
    sections: Optional[List[Dict[str, Any]]] = Field(None, description="List of sections in the paper.")
    references: Optional[List[Dict[str, Any]]] = Field(None, description="List of references in the paper.")

    # PDF processing metadata (optional - added when PDF is processed)
    parser_used: Optional[str] = Field(None, description="The parser used to process the PDF.")
    parser_metadata: Optional[Dict[str, Any]] = Field(None, description="Metadata about the parsing process.")
    pdf_processed: Optional[bool] = Field(False, description="Whether the PDF has been processed.")
    pdf_processing_date : Optional[datetime] = Field(None, description="The date when the PDF was processed.")

class PaperResponse(PaperBase):
    """Schema for paper API responses with all content."""
    id: UUID = Field(..., description="The unique identifier for the paper record.")
    
    # parsed content
    raw_text: Optional[str] = Field(None, description="The raw text content of the paper.")
    sections: Optional[List[Dict[str, Any]]] = Field(None, description="List of sections in the paper.")
    references: Optional[List[Dict[str, Any]]] = Field(None, description="List of references in the paper.")
    
    # PDF processing metadata
    parser_used: Optional[str] = Field(None, description="The parser used to process the PDF.")
    parser_metadata: Optional[Dict[str, Any]] = Field(None, description="Metadata about the parsing process.")
    pdf_processed: Optional[bool] = Field(False, description="Whether the PDF has been processed.")
    pdf_processing_date : Optional[datetime] = Field(None, description="The date when the PDF was processed.")
    
    # timestamps
    created_at: datetime = Field(..., description="The date when the paper record was created.")
    updated_at: datetime = Field(..., description="The date when the paper record was last updated.")
    
    class Config:
        from_attributes = True

class PaperSearchResponse(BaseModel):
    paper: List[PaperResponse] = Field(..., description="List of papers matching the search criteria.")
    total: int = Field(..., description="Total number of papers matching the search criteria.")