"""API test configuration and fixtures."""

import pytest 
from asgi_lifespan import LifespanManager 
from httpx import ASGITransport, AsyncClient 
from src.main import app 

@pytest.fixture(scope="session")
def anyio_backend():
    """Set the AnyIO backend to asyncio for testing."""
    return "asyncio"

@pytest.fixture(scope="session")
async def test_client():
    """Fixture for creating an asynchronous test client for the FastAPI app."""
    async with LifespanManager(app) as manager:
        async with AsyncClient(transport  = ASGITransport(app=app), base_url="http://test") as client:
            yield client



