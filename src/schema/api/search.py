from typing import List, Optional 
from pydantic import BaseModel, Field

class SearchRequest(BaseModel):
    """Request model for search queries."""
    query: str = Field(...,min_length=1, max_length=500, description = "Search query across title, abstract, and authors.")
    size: int = Field(default = 10, ge = 1, le = 100, description = "Number of results to return")
    from_: int = Field(default = 0, ge = 0, alias = "from", description = "Offset for pagination, starting from 0" )
    categories: Optional[List[str]] = Field(default = None, description = "List of categories to filter the search results")
    latest_papers: bool = Field(default = False, description = "sort by publicaiton date(newest first) if True, else sort by relevance")

class SearchHit(BaseModel):
    """Individual search result."""

    arxiv_id: str
    title: str
    authors: Optional[str]
    abstract: Optional[str]
    published_date: Optional[str]
    pdf_url: Optional[str]
    score: float
    highlights: Optional[dict] = None
    
class SearchResponse(BaseModel):
    """search response model """
    query: str 
    total : int 
    hits: List[SearchHit]
    error: Optional[str] = None