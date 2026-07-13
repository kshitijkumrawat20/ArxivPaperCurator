from typing import Dict, List
from pydantic import BaseModel

class JinaEmbeddingRequest(BaseModel):
    """Request model for Jina embedding API."""
    model : str = "jina-embeddings-v3"
    task: str = "retrieval.passage" # or "retrieval.query" for queries
    dimensions: int = 1024
    late_chunking: bool = False # late chunking means that the text will be chunked after the embedding is generated, rather than before. This can be useful for long documents where you want to generate a single embedding for the entire document, rather than multiple embeddings for each chunk.
    embedding_type: str = "float"
    input: List[str]

class JinaEmbeddingResponse(BaseModel):
    """Response model for Jina embeddings API."""
    model: str 
    object: str = "list"
    usage: Dict[str, int] # usage is a dictionary that contains the number of tokens used for the request and response.
    data : List[Dict] # data is a list of dictionaries, each containing an embedding for a text input.
