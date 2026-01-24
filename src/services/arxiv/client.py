import asyncio 
import logging 
import time
import xml.etree.ElementTree as ET 
from functools import cached_property
from pathlib import Path 
from typing import Dict, List, Optional
from urllib.parse import quote, urlencode
import httpx 
from src.config import ArxivSettings
from exceptions import ArxivAPIException, ArxivAPITimeoutError , ArxivParseError, PDFDownloadException,PDFDownloadTimeoutError
from src.schemas.arxiv.paper import ArxivPaper

logger = logging.getLogger(__name__)

class ArxivClient: 
    """Client for interacting with the arXiv API."""

    def __init__(self, settings: ArxivSettings):
        self._settings = settings # _settings is private attribute following OOP convention of prefixing with underscore for internal use and showing OOPS encapsulation
        self._last_request_time : Optional[float] = None

        @cached_property # caches the property value after first computation
        def pdf_cache_dir(self) -> Path: 
            """PDF cache directory."""
            cache_dir = Path(self._settings.pdf_cache_dir)
            cache_dir.mkdir(parents=True, exist_ok=True)
            return cache_dir


    @property
    def base_url(self) -> str: 
        return self._settings.base_url
    
    @property 
    def namespace(self) -> Dict[str, str]:
        return self._settings.namespace
    @property 
    def rete_limit_delay(self) -> float:
        return self._settings.rate_limit_delay
    @property 
    def timeout_secs(self) -> int:
        return self._settings.timeout_secs
    @property
    def max_results_per_query(self) -> int:
        return self._settings.max_results_per_query
    @property
    def search_category(self) -> str:
        return self._settings.search_category
    @property
    def download_max_retries(self) -> int:
        return self._settings.download_max_retries
    @property
    def download_retry_delay_secs(self) -> float:
        return self._settings.download_retry_delay_secs
    @property
    def max_concurrent_downloads(self) -> int:
        return self._settings.max_concurrent_downloads
    @property
    def max_concurrent_parsing(self) -> int:
        return self._settings.max_concurrent_parsing
    
    async def fetch_papers(
            self,
            max_results: Optional[int] = None,
            start: int = 0, 
            sort_by: str = "submittedDate", # default to most recent papers
            sort_order: str = "descending", # default to descending order
            from_date: Optional[str] = None,
            to_date: Optional[str]= None ) -> List[ArxivPaper]:
        """Fetch papers from arXiv API based on search criteria.
        
        Args:
            max_results (Optional[int]): Maximum number of results to fetch.
            start (int): Starting index for results.
            sort_by (str): Field to sort by.
            sort_order (str): Order of sorting.
            from_date (Optional[str]): Start date for filtering (YYYY-MM-DD).
            to_date (Optional[str]): End date for filtering (YYYY-MM-DD).
        Return: 
            List of ArxivPaper instances
        """
        if max_results is None:
            max_results = self.max_results_per_query

        # build search query 
        search_query = f"cat:{self.search_category}"

        # add date filters if provided 
        if from_date: 
            ## converting dates to arxiv format YYYYMMDDHHMMSS
            date_from = f"{from_date}000000" if from_date else "*" 
            date_to = f"{to_date}2359" if to_date else "*"  

            # use correct arxiv api syntax with + symbol 
            search_query += f" AND submittedDate:[{date_from}+TO+{date_to}]"

        params = {
            "search_query": search_query,
            "start": start,
            "max_results": max_results,
            "sortBy": sort_by,
            "sortOrder": sort_order
        }
        safe = ":+[]" # characters to not encode, needed for arxiv syntax
        url = f"{self.base_url}?{urlencode(params, quote_via=quote, safe=safe)}"

    

    
        