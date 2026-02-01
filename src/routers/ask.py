from fastapi import APIRouter
from src.schemas.ask import AskRequest, AskResponse, Papersource

router = APIRouter() 

@router.post("/ask", response_model = AskResponse)
async def ask_question(request: AskRequest) -> AskResponse:
    """
    Endpoint to ask questions about research papers.

    """

    mock_source = [
        Papersource(
            arxiv_id="2101.00001",
            title="Sample Paper Title",
            author=["Author One", "Author Two"],
            abstract_preview="This is a sample abstract preview of the paper."
        ),
        Papersource(
            arxiv_id="2101.00002",
            title="Another Sample Paper Title",
            author=["Author Three", "Author Four"],
            abstract_preview="This is another sample abstract preview of the paper."
        )
    ]
    return AskResponse(
        answer="This is a mock answer to your questions based on the provided papers.",
        source  = mock_source
    )
