from typing import Any

import pytest

from src.config import Settings
from src.services.embeddings.factory import make_embeddings_service
from src.services.embeddings.jina_client import JinaEmbeddingsClient


class FakeResponse:
    def __init__(self, payload: dict[str, Any]):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self._payload


@pytest.mark.anyio
async def test_make_embeddings_service_uses_settings_api_key() -> None:
    settings = Settings(_env_file=None, debug=True, environment="development", jina_api_key="test-api-key")

    client = make_embeddings_service(settings=settings)

    assert isinstance(client, JinaEmbeddingsClient)
    assert client.api_key == "test-api-key"
    assert client.headers["Authorization"] == "Bearer test-api-key"

    await client.close()


@pytest.mark.anyio
async def test_embed_passages_returns_embeddings_when_api_responds(monkeypatch: pytest.MonkeyPatch) -> None:
    client = JinaEmbeddingsClient(api_key="test-api-key")
    captured: dict[str, Any] = {}

    async def fake_post(url: str, headers: dict[str, str] | None = None, json: dict[str, Any] | None = None):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        return FakeResponse(
            {
                "model": "jina-embeddings-v3",
                "object": "list",
                "usage": {"prompt_tokens": 2, "total_tokens": 2},
                "data": [
                    {"embedding": [0.1, 0.2, 0.3]},
                    {"embedding": [0.4, 0.5, 0.6]},
                ],
            }
        )

    monkeypatch.setattr(client.client, "post", fake_post)

    embeddings = await client.embed_passages(["paper one", "paper two"])

    assert len(embeddings) == 2
    assert embeddings[0] == [0.1, 0.2, 0.3]
    assert embeddings[1] == [0.4, 0.5, 0.6]
    assert captured["url"].endswith("/embeddings")
    assert captured["headers"]["Authorization"] == "Bearer test-api-key"
    assert captured["json"]["input"] == ["paper one", "paper two"]

    await client.close()