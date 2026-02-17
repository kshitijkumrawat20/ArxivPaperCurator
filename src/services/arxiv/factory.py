"""
Factory module for creating instances of ArXivPaperCurator and related components.
"""

from src.config import get_settings

from .client import ArxivClient

def make_arxiv_client() -> ArxivClient:
    """
    Factory function to create an instance of ArxivClient based on configuration settings.
    Returns:
        An instance of ArxivClient.
    """
    settings = get_settings()
    client = ArxivClient(settings=settings.arxiv)
    return client
