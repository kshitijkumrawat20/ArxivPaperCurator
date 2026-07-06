from enum import Enum 
from typing import Any,Dict, List, Optional 
from pydantic import BaseModel, Field 

class ParserType(str, Enum):
    """Enumeration for different types of parsers."""
    DOCLING = "docling"

class PaperSection(BaseModel):
    """REPRESENTS A SECTION OF A PAPER WITH ITS TITLE AND CONTENT"""

    title: str = Field(..., description= "Section title")
    content: str = Field(..., description= "Section content")
    level: int = Field(..., description= "Section level in the hierarchy", example= 1)

class PaperFigure(BaseModel):
    """Represents a figure in a paper."""

    caption: str = Field(..., description= "Figure caption")
    id: str = Field(..., description= "Unique identifier for the figure")

class PaperTable(BaseModel):
    """Represents a table in a paper."""

    caption: str = Field(..., description= "Table caption")
    id: str = Field(..., description= "Unique identifier for the table")

class PdfContent(BaseModel):
    """Represents the content of a PDF paper."""

    sections: List[PaperSection] = Field(default_factory=list, description= "List of sections in the paper")
    figures: List[PaperFigure] = Field(default_factory=list, description= "List of figures in the paper")
    tables: List[PaperTable]= Field(default_factory=list, description= "List of tables in the paper")
    raw_text: str= Field(..., description= "Raw text extracted from the PDF")
    references: List[str] = Field(default_factory=list, description= "List of references cited in the paper")
    parser_used: ParserType = Field(..., description= "Type of parser used to extract the content")
    metadata: Dict[str, Any] = Field(default_factory=dict, description= "Additional metadata related to the PDF content")

class ArxivMetadata(BaseModel): 
    """Represents metadata from ArXiv Api."""

    title: str = Field(..., description= "Title of the paper")
    authors: List[str] = Field(default_factory=list, description= "List of authors of the paper")
    abstract: str = Field(..., description= "Abstract of the paper")
    categories: List[str] = Field(default_factory=list, description= "List of categories associated with the paper")
    published_date: str = Field(..., description= "Publication date of the paper")
    pdf_url: str = Field(..., description= "URL to download the PDF version of the paper")

class ParsedPaper(BaseModel):
    """Represents a parsed paper with its metadata and content."""

    arxiv_metadata: ArxivMetadata = Field(..., description= "Metadata from ArXiv API")
    pdf_content: Optional[PdfContent] = Field(None, description= "Content extracted from the PDF")