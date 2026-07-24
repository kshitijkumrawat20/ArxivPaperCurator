import json
import logging 
from typing import Iterator 
import gradio as gr
import httpx

logger = logging.getLogger(__name__)

# configuration 
API_BASE_URL = "http://localhost:8000/api/v1"  
DEFAULT_MODEL = "llama3.2:1b" 
AVAILABLE_CATEGORIES = ["cs.AI", "cs.LG"]

async def stream_response(
        query: str,
        top_k: int = 3, 
        use_hybrid: bool = True,
        model: str = DEFAULT_MODEL,
        categories: list[str] = ""

) -> Iterator[str]:
    """ 
    Stream the response from the RAG API for a given query.
    """
    if not query.strip():
        yield "Please enter a valid query."
        return
    
    # Parse categories
    category_list = 