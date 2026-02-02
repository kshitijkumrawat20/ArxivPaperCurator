"""Ollama client for interacting with Ollama LLM service."""

import httpx
from typing import Optional, Dict, Any, List


class OllamaClient:
    """
    Client for interacting with Ollama API.
    
    Ollama ek local LLM server hai jo LLMs (like Llama, Mistral) ko locally run karta hai.
    Ye client usse communicate karta hai HTTP ke through.
    """

    def __init__(self, settings):
        """
        Initialize OllamaClient with settings.
        
        Args:
            settings: Application settings containing Ollama configuration
        """
        self.host = settings.ollama_host
        self.model = settings.ollama_model
        self.timeout = settings.ollama_timeout

    async def health_check(self) -> Dict[str, str]:
        """
        Check if Ollama service is healthy and reachable.
        
        Returns:
            Dict with status and available models
        """
        async with httpx.AsyncClient(timeout=10) as client:
            # Check if Ollama is running
            response = await client.get(f"{self.host}/api/tags")
            response.raise_for_status()
            
            models = response.json().get("models", [])
            model_names = [m.get("name", "") for m in models]
            
            return {
                "status": "healthy",
                "models": model_names,
                "host": self.host
            }

    async def generate(
        self,
        prompt: str,
        model: Optional[str] = None,
        system: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> str:
        """
        Generate text completion using Ollama.
        
        Args:
            prompt: The input prompt for generation
            model: Model to use (defaults to configured model)
            system: Optional system prompt
            temperature: Sampling temperature (0-1)
            max_tokens: Maximum tokens to generate
            
        Returns:
            Generated text response
        """
        model = model or self.model
        
        payload: Dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
            }
        }
        
        if system:
            payload["system"] = system
            
        if max_tokens:
            payload["options"]["num_predict"] = max_tokens

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.host}/api/generate",
                json=payload
            )
            response.raise_for_status()
            return response.json().get("response", "")

    async def chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
    ) -> str:
        """
        Chat completion using Ollama.
        
        Args:
            messages: List of chat messages [{"role": "user", "content": "..."}]
            model: Model to use (defaults to configured model)
            temperature: Sampling temperature
            
        Returns:
            Assistant's response text
        """
        model = model or self.model
        
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
            }
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.host}/api/chat",
                json=payload
            )
            response.raise_for_status()
            return response.json().get("message", {}).get("content", "")

    async def embeddings(
        self,
        text: str,
        model: str = "nomic-embed-text",
    ) -> List[float]:
        """
        Generate embeddings for text using Ollama.
        
        Args:
            text: Text to embed
            model: Embedding model to use
            
        Returns:
            List of embedding floats
        """
        payload = {
            "model": model,
            "prompt": text,
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.host}/api/embeddings",
                json=payload
            )
            response.raise_for_status()
            return response.json().get("embedding", [])

    async def list_models(self) -> List[Dict[str, Any]]:
        """
        List all available models in Ollama.
        
        Returns:
            List of model information dictionaries
        """
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(f"{self.host}/api/tags")
            response.raise_for_status()
            return response.json().get("models", [])
