from enum import Enum
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field

class ParserType(str, Enum): 
    """PDF parser types."""
    DOCLING = "docling"
    GROBID = "grobid"

class PaperSection(BaseModel):
    """Represents a section of a paper."""
    title : str = Field(..., description="The title of the section.")
    content: str = Field(..., description="The textual content of the section.")
    level : Optional[int] = Field(None, description="The hierarchical level of the section (e.g., 1 for top-level, 2 for subsections).")

class PaperFigure(BaseModel):
    """Represents a figure in the paper."""
    caption: Optional[str] = Field(None, description="The caption of the figure.")
    id : str = Field(..., description="The unique identifier for the figure.")

class PaperTable(BaseModel):
    """Represents a table in the paper."""
    caption: Optional[str] = Field(None, description="The caption of the table.")
    id : str = Field(..., description="The unique identifier for the table.")

class PdfContent(BaseModel):
    """ Pdf specific content extracted by parser like Docling"""

    sections: List[PaperSection] = Field(default_factory = list, description="List of sections in the paper.")
    figures: List[PaperFigure] = Field(default_factory = list, description="List of figures in the paper.")
    tables: List[PaperTable] = Field(default_factory = list, description="List of tables in the paper.")
    raw_text: str = Field(..., description="Extracted raw text content of the paper.")
    references: List[str] = Field(default_factory = list, description="List of references cited in the paper.")
    parser_used: ParserType = Field(..., description="The parser used to extract content from the PDF.")
    metadata: Dict[str, Any] = Field(default_factory = dict, description="Additional metadata about the parsing process.")

class ArxivMetadata(BaseModel): 
    """Core arXiv metadata for a paper."""
    title: str = Field(..., description="The title of the arXiv paper.")
    authors: List[str] = Field(..., description="List of authors of the arXiv paper.")
    abstract: str = Field(..., description="The abstract of the arXiv paper.")  
    arxiv_id: str = Field(..., description="The unique identifier for the arXiv paper.")
    categories: List[str] = Field(default_factory=list, description="List of categories the paper belongs to.")
    published_date: str = Field(..., description="The publication date of the arXiv paper.")
    pdf_url: str = Field(..., description="The URL to download the PDF of the arXiv paper.")

class ParsedPaper(BaseModel):
    """Schema representing a parsed arXiv paper with metadata and content."""
    arxiv_metadata: ArxivMetadata = Field(..., description="Core metadata of the arXiv paper.")
    pdf_content: Optional[PdfContent] = Field(None, description="Parsed content extracted from the PDF of the paper.")