from typing import Optional 
from pydantic import BaseModel 

class ChunkMetadata(BaseModel):
    """Metadata for a text chunk"""
    chunk_index: int 
    start_char: int 
    end_char: int 
    word_count: int 
    overlap_with_previous_chunk: int 
    overlap_with_next_chunk: int 
    section_title: Optional[str] = None

class TextChunk(BaseModel):
    """Represents a chunk of text with associated metadata."""
    text: str
    metadata: ChunkMetadata 
    arxiv_id : str
    paper_id : str
