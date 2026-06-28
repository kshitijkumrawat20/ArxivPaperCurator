from fastapi import APIRouter, Depends
from src.schema.ask import AskRequest, AskResponse, PaperSource, 

router = APIRouter()

@router.post("/ask", response_model=AskResponse, tags=["Ask"])
async def ask_question(request: AskRequest) -> AskResponse: 
    """
    Mock endpoint for now 
    """
    mock_sources = [
        PaperSource(
            arxiv_id="2401.00001",
            title="Mock Paper: Introduction to AI Research",
            authors=["John Doe", "Jane Smith"],
            abstract_preview="This is a mock abstract for testing purposes in week 1...",
        ),
        PaperSource(
            arxiv_id="2401.00002",
            title="Mock Paper: Advanced Machine Learning Techniques",
            authors=["Alice Johnson", "Bob Wilson"],
            abstract_preview="Another mock abstract demonstrating the API structure...",
        ),
    ]

    return AskResponse(
        answer="This is a mock answer to your question based on the provided sources.",
        sources = mock_sources
    )