from typing import List, Optional 
from pydantic import BaseModel, Field

class SearchRequest(BaseModel):
    """Request model for search queries."""
    query: str = Field(...,min_length=1, max_length=500, description = "Search query across title, abstract, and authors.")
    size: int = Field(default = 10, ge = 1, le = 100, description = "Number of results to return")
    from_: int = Field(default = 0, ge = 0, alias = "from", description = "Offset for pagination, starting from 0" )
    categories: Optional[List[str]] = Field(default = None, description = "List of categories to filter the search results")
    latest_papers: bool = Field(default = False, description = "sort by publicaiton date(newest first) if True, else sort by relevance")

class HybridSearchRequest(BaseModel):
    """Request model for hybrid search supporting all search modes"""

    query: str = Field(..., description= "Search quer text", min_length= 1, max_length  = 500)
    size: int = Field(10,description="Number of results to return", ge = 1, le = 100)
    from_: int = Field(0, description = "Offset for pagination, starting from 0", ge = 0, alias = "from")
    categories: Optional[List[str]] = Field(None, description= "Filter by arxiv categoies (e.g. cs.AI, cs.LG, stat.ML)")
    latest_papers: bool = Field(False, description= "Sort by publication date (newest first) if True, else sort by relevance")
    use_hybrid : bool = Field(True, description= "Use hybrid search (BM25 + embeddings) if True, else use BM25 only")
    min_score: float = Field(0.0, description= "Minimum score threshold for filtering results (default: 0.0)", ge = 0.0)

    class Config: 
        allow_population_by_field_name = True  # Allow population of model using field names, even if they have aliases. This is useful for fields like 'from_' which have an alias 'from' but can still be populated using 'from_'.
        json_schema_extra = {
            "example": {
                "query": "machine learning",
                "size": 10,
                "categories": ["cs.AI", "cs.LG"],
                "latest_papers": False,
                "use_hybrid": True,
            }
        }

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

    # chunk specific fields
    chunk_text: Optional[str] = Field(None, description = "text content of the machining chunk")
    chunk_id : Optional[str] = Field(None, description = "unique id of the chunk")
    section_name: Optional[str] = Field(None, description = "section name of the chunk")
    
class SearchResponse(BaseModel):
    """search response model """
    query: str 
    total : int 
    hits: List[SearchHit]
    size: int = Field(description = "Number of results requested")
    from_: int = Field(alias = "from", description = "Offset used for pagination")
    search_mode: Optional[str] = Field(description = "Search mode used (BM25, Hybrid, Embeddings)")
    error: Optional[str] = None

    class Config:
        allow_population_by_field_name = True  