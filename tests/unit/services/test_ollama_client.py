from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.ollama.client import OllamaClient


@pytest.fixture
def ollama_client() -> OllamaClient:
    settings = SimpleNamespace(ollama_host="http://ollama:11434", ollama_timeout=30)
    return OllamaClient(settings)


@pytest.mark.asyncio
async def test_generate_returns_ollama_response(ollama_client: OllamaClient) -> None:
    response = MagicMock(status_code=200)
    response.json.return_value = {"response": "Attention mechanisms weigh relevant inputs."}

    with patch("httpx.AsyncClient") as async_client:
        async_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=response)

        result = await ollama_client.generate("llama3.2:3b", "Explain attention mechanisms.")

    assert result["response"] == "Attention mechanisms weigh relevant inputs."
    assert "usage_metadata" in result
