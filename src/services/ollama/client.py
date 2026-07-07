import logging 
from typing import Dict , List, Any, Optional
import httpx 
from src.config import Settings
from src.exception import OllamaConnectionError, OllamaException, OllamaTimeoutError

logger = logging.getLogger(__name__)

class OllamaClient: 
    """Ollama client for health checks"""

    def __init__(self, settings: Settings):
        self.base_url = settings.ollama_host
        self.timeout = httpx.Timeout(float(settings.ollama_timeout))
        
    async def health_check(self) -> Dict[str, str]:
        """Checking if ollama service is available and healthy"""
        try: 
            async with httpx.AsyncClient(timeout=self.timeout) as client: 
                response = await client.get(f"{self.base_url}/api/tags")
                if response.status_code == 200: 
                    version_data = response.json()
                    return {"status": "healthy", "message": "Ollama service is available.", "version": version_data.get("version", "Unknown")}
                else: 
                    return {"status": "unhealthy", "message": f"Ollama service returned status code {response.status_code}."}
        except Exception as e : 
            logger.error(f"Error during Ollama health check: {e}")
            return {"status": "unhealthy", "message": f"Error during health check: {e}"}
    
    async def list_models(self) -> List[Dict[str, Any]]:
        """
        Get list of available models 
        Returns : 
        List of model inforamtion dictionaries 
        """

        try: 
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(f"{self.base_url}/api/tags")

                if response.status_code == 200:
                    data = response.json()
                    return data.get("models", [])
                else:
                    raise OllamaException(f"Failed to list models: {response.status_code}")

        except httpx.ConnectError as e:
            raise OllamaConnectionError(f"Cannot connect to Ollama service: {e}")
        except httpx.TimeoutException as e:
            raise OllamaTimeoutError(f"Ollama service timeout: {e}")
        except OllamaException:
            raise
        except Exception as e:
            raise OllamaException(f"Error listing models: {e}")

    async def generate(self, model: str, prompt: str, stream: bool = False, **kwargs) -> Optional[Dict[str, Any]]:
        """
        Generate text using specified model.

        Args:
            model: Model name to use
            prompt: Input prompt for generation
            stream: Whether to stream response (not implemented)
            **kwargs: Additional generation parameters

        Returns:
            Response dictionary or None if failed
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                data = {"model": model, "prompt": prompt, "stream": stream, **kwargs}

                response = await client.post(f"{self.base_url}/api/generate", json=data)

                if response.status_code == 200:
                    return response.json()
                else: 
                    raise OllamaException(f"Generation failed: {response.status_code}")

        except httpx.ConnectError as e:
            raise OllamaConnectionError(f"Cannot connect to Ollama service: {e}")
        except httpx.TimeoutException as e:
            raise OllamaTimeoutError(f"Ollama service timeout: {e}")
        except OllamaException:
            raise
        except Exception as e:
            raise OllamaException(f"Error generating with Ollama: {e}")
