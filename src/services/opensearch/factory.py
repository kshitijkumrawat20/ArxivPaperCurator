"""Unified factory for Opensearch client"""

from functools import lru_cache
from typing import Optional 
from src.config import Settings,  get_settings

from .client import OpenSearchClient


@lru_cache(maxsize=1)
def make_opensearch_client(settings: Optional[Settings] = None) -> OpenSearchClient:
    """Factory function to create cached OpenSearch client.

    Uses lru_cache to maintain a singleton instance.
    Uses lru_cache to maintain a singleton instance for efficiency.
    :param settings: Optional Settings object; if None, retrieves from get_settings()
    :returns: Cached OpenSearch client
    :rtype: OpenSearchClient
    """
    if settings is None:
        settings = get_settings()
    return OpenSearchClient(host=settings.opensearch.host, settings=settings)

def make_opensearch_client_fresh(settings: Optional[Settings]=None, host: Optional[str] = None) -> OpenSearchClient:
    """Factory function to create a fresh OpenSearch client instance.

    :param settings: Optional Settings object; if None, retrieves from get_settings()
    :param host: Optional host URL; if provided, overrides settings.opensearch.host
    :returns: New OpenSearch client instance
    :rtype: OpenSearchClient
    """
    if settings is None:
        settings = get_settings()

    opensearch_host = host or settings.opensearch.host
    return OpenSearchClient(host=opensearch_host, settings=settings)
