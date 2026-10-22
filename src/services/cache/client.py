import hashlib
import json
import logging
from datetime import timedelta
from typing import Any, Optional

from src.config import RedisSettings
from src.schema.api.ask import AskRequest, AskResponse, PaperAskRequest, PaperAskResponse

logger = logging.getLogger(__name__)


class CacheClient:
    """Redis-based exact match cache for RAG queries."""

    def __init__(self, redis_client: Any, settings: RedisSettings):
        self.redis = redis_client
        self.settings = settings
        self.ttl = timedelta(hours=settings.ttl_hours)

    def _generate_cache_key(
        self, request: AskRequest | PaperAskRequest, paper_id: Optional[str] = None
    ) -> str:
        """Generate exact cache key based on request parameters."""
        key_data = {
            "query": request.query,
            "model": request.model,
            "top_k": request.top_k,
            "use_hybrid": request.use_hybrid,
            "categories": sorted(getattr(request, "categories", None) or []),
        }
        # Keep the legacy global key unchanged while isolating paper-scoped answers
        # from both global answers and answers for other exact arXiv versions.
        if paper_id is not None:
            key_data["scope"] = "paper"
            key_data["arxiv_id"] = paper_id
        key_string = json.dumps(key_data, sort_keys=True)
        key_hash = hashlib.sha256(key_string.encode()).hexdigest()[:16]
        return f"exact_cache:{key_hash}"

    async def find_cached_response(self, request: AskRequest) -> Optional[AskResponse]:
        """Find cached response for exact query match."""
        try:
            cache_key = self._generate_cache_key(request)

            # Simple Redis GET operation - O(1)
            cached_response = self.redis.get(cache_key)

            if cached_response:
                try:
                    response_data = json.loads(cached_response)
                    logger.info(f"Cache hit for exact query match")
                    return AskResponse(**response_data)
                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to deserialize cached response: {e}")
                    return None

            return None

        except Exception as e:
            logger.error(f"Error checking cache: {e}")
            return None

    async def store_response(self, request: AskRequest, response: AskResponse) -> bool:
        """Store response for exact query matching."""
        try:
            cache_key = self._generate_cache_key(request)

            # Simple Redis SET operation with TTL
            success = self.redis.set(cache_key, response.model_dump_json(), ex=self.ttl)

            if success:
                logger.info(f"Stored response in exact cache with key {cache_key[:16]}...")
                return True
            else:
                logger.warning(f"Failed to store response in cache")
                return False

        except Exception as e:
            logger.error(f"Error storing in cache: {e}")
            return False

    async def find_cached_paper_response(
        self, request: PaperAskRequest, paper_id: str
    ) -> Optional[PaperAskResponse]:
        try:
            value = self.redis.get(self._generate_cache_key(request, paper_id=paper_id))
            if not value:
                return None
            return PaperAskResponse.model_validate_json(value)
        except Exception as e:
            logger.warning("Error checking paper-scoped cache: %s", e)
            return None

    async def store_paper_response(
        self, request: PaperAskRequest, paper_id: str, response: PaperAskResponse
    ) -> bool:
        try:
            return bool(
                self.redis.set(
                    self._generate_cache_key(request, paper_id=paper_id), response.model_dump_json(), ex=self.ttl
                )
            )
        except Exception as e:
            logger.warning("Error storing paper-scoped response in cache: %s", e)
            return False
