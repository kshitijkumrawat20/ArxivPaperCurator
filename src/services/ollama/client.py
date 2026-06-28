import logging 
from typing import Dict 
import httpx 
from src.config import Settings

logger = logging.getLogger(__name__)

class OllamaClient: 
    """Ollama client for health checks"""

    def __init__(self, settings: Settings):
        self.base_url = settings.ollama_host: 
        
    async def health_check(self) -> Dict[str, str]:
        """Checking if ollama service is available and healthy"""
        try: 
            async with httpx.AsyncClient() as client: 
                response = await client.get(f"{self.base_url}/api/tags")
                if response.status_code == 200: 
                    return {"status": "healthy", "message": "Ollama service is available."}
                else: 
                    return {"status": "unhealthy", "message": f"Ollama service returned status code {response.status_code}."}
        except Exception as e : 
            logger.error(f"Error during Ollama health check: {e}")
            return {"status": "unhealthy", "message": f"Error during health check: {e}"}