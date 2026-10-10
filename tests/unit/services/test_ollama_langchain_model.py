from types import SimpleNamespace
from unittest.mock import patch

from src.services.ollama.client import OllamaClient


def test_get_langchain_model_uses_client_configuration() -> None:
    settings = SimpleNamespace(ollama_host="http://ollama:11434", ollama_timeout=30)
    client = OllamaClient(settings)

    with patch("src.services.ollama.client.ChatOllama") as chat_ollama:
        client.get_langchain_model("llama3.2:3b", temperature=0.2)

    chat_ollama.assert_called_once_with(
        model="llama3.2:3b",
        base_url="http://ollama:11434",
        temperature=0.2,
    )
