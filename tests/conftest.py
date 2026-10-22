"""Main test configuration and fixtures."""

import pytest 
from polyfactory.factories.pydantic_factory import ModelFactory # auto generate test data for pydantic models
from src.config import Settings 
from src.schema.api.ask import AskRequest
from src.schema.arxiv.paper import PaperCreate, PaperResponse

@pytest.fixture # act like the depend of fastapi 
def settings() -> Settings:
    """Test settings fixtures"""
    return Settings()

class PaperCreateFatory(ModelFactory[PaperCreate]): ...

class PaperResponseFactory(ModelFactory[PaperResponse]): ...

class AskRequestFactory(ModelFactory[AskRequest]): ...


@pytest.fixture
def paper_create_data() -> PaperCreate:
    """Fixture for generating PaperCreate test data."""
    return PaperCreateFatory.build()

@pytest.fixture
def paper_response_data() -> PaperResponse:
    """Mock paper response data."""
    return PaperResponseFactory.build()


@pytest.fixture
def ask_request_data() -> AskRequest:
    """Mock ask request data."""
    return AskRequestFactory.build()
