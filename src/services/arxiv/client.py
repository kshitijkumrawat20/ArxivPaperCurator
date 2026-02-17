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
from src.exceptions import ArxivAPIException, ArxivAPITimeoutError , ArxivParseError, PDFDownloadException,PDFDownloadTimeoutError
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
    def rate_limit_delay(self) -> float:
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

        try: 
            logger.info(f"Fetching {max_results} papers from arxiv ")

            ## adding rate limiting between all requests 
            if self._last_request_time is not None:
                time_since_last_request = time.time() - self._last_request_time
                if time_since_last_request < self.rate_limit_delay: 
                    sleep_time = self.rate_limit_delay - time_since_last_request
                    await asyncio.sleep(sleep_time)
                self._last_request_time = time.time()   ## after the sleep update the last request time

            async with httpx.AsyncClient() as client:
                response = await client.get(url)
                response.raise_for_status()
                xml_data = response.text 
            
            papers = self._parse_response(xml_data)
            logger.info(f"Fetched {len(papers)} papers from arXiv")
            return papers

        except httpx.TimeoutException as e:
            logger.error(f"Timeout error fetching papers from arXiv: {e}")
            raise ArxivAPITimeoutError(f"Timeout error fetching papers from arXiv: {e}") 
        except httpx.HTTPError as e:
            logger.error(f"HTTP error fetching papers from arXiv: {e}")
            raise ArxivAPIException(f"HTTP error fetching papers from arXiv: {e}")
        except Exception as e:
            logger.error(f"Unexpected error fetching papers from arXiv: {e}")
            raise ArxivAPIException(f"Unexpected error fetching papers from arXiv: {e}")
        
    async def fetch_paper_with_query(
            self, 
            search_query: str, 
            max_results: Optional[int] = None, 
            start: int = 0, 
            sort_by: str = "submittedDate",
            sort_order: str = "descending",  # or "ascending"
    ) -> List[ArxivPaper]:
        """
        Fetch papers from arXiv API based on a custom search query.
        Args:
            search_query (str): The search query string.
            max_results (Optional[int]): Maximum number of results to fetch.
            start (int): Starting index for results.
            sort_by (str): Field to sort by.
            sort_order (str): Order of sorting.
        Returns:
            List of ArxivPaper instances.

        """
        if max_results is None: 
            max_results = self.max_results_per_query
        params = {
            "search_query": search_query,
            "start": start,
            "max_results": max_results,
            "sortBy": sort_by,
            "sortOrder": sort_order
        }
        safe = ":+[]" # characters to not encode, needed for arxiv syntax
        url = f"{self.base_url}?{urlencode(params, quote_via=quote, safe=safe)}"



    async def fetch_papers_by_id(self, arxiv_id: str ) -> Optional[ArxivPaper]:
        """Fetch a single paper by its arXiv ID.
        Args:
            arxiv_id (str): The arXiv ID of the paper to fetch.
        Returns:
            Optional[ArxivPaper]: The fetched paper or None if not found.
        """

        ## remove the version suffix if present
        cleaned_id = arxiv_id.split("v")[0] if "v" in arxiv_id else arxiv_id 

        params = {
            "id_list": cleaned_id, 
            "max_results" : 1
        }

        safe = ":+[]*" # characters to not encode, needed for arxiv syntax
        url = f"{self.base_url}?{urlencode(params, quote_via=quote, safe=safe)}"

        try: 
            if self._last_request_time is not None: 
                time_since_last_request = time.time() - self._last_request_time
                if time_since_last_request < self.rate_limit_delay:
                    sleep_time = self.rate_limit_delay - time_since_last_request
                    await asyncio.sleep(sleep_time)

            self._last_request_time = time.time()

            async with httpx.AsyncClient() as client:
                response = await client.get(url) 
                response.raise_for_status()
                xml_data = response.text
            papers = self._parse_response(xml_data)
            logger.info(f"Fetched paper with arXiv ID {arxiv_id} from arXiv")
            return papers 
        except httpx.TimeoutException as e:
            logger.error(f"Timeout error fetching paper {arxiv_id} from arXiv: {e}")
            raise ArxivAPITimeoutError(f"Timeout error fetching paper {arxiv_id} from arXiv: {e}")
        except httpx.HTTPError as e:
            logger.error(f"HTTP error fetching paper {arxiv_id} from arXiv: {e}")
            raise ArxivAPIException(f"HTTP error fetching paper {arxiv_id} from arXiv: {e}")
        except Exception as e:
            logger.error(f"Unexpected error fetching paper {arxiv_id} from arXiv: {e}")
            raise ArxivAPIException(f"Unexpected error fetching paper {arxiv_id} from arXiv: {e}")
        

    def _parse_response(self, xml_data: str) -> List[ArxivPaper]:
        """Parse the XML response from arXiv API and extract paper details.
        
        Args:
            xml_data (str): XML response data from arXiv API.
        Returns: 
            List of ArxivPaper instances.
        """
        try: 
            root = ET.fromstring(xml_data)
            entries = root.findall("atom:entry", self.namespace) # # atom is a standard XML namespace for Atom feeds
            papers = []
            for entry in entries:
                paper = self._parse_single_entry(entry)
                if paper: 
                    papers.append(paper)
                return papers 
        except ET.ParseError as e:
            logger.error(f"Error parsing arXiv XML response: {e}")
            raise ArxivParseError(f"Error parsing arXiv XML response: {e}")
        except Exception as e:
            logger.error(f"Unexpected error parsing arXiv XML response: {e}")
            raise ArxivParseError(f"Unexpected error parsing arXiv XML response: {e}")
    
    def _parse_single_entry(self, entry: ET.Element) -> Optional[ArxivPaper]:
        """Parse a single entry from the arXiv API response.
        Args: 
            entry (ET.Element): XML element representing a single paper entry.
        Returns:
            Optional[ArxivPaper]: Parsed ArxivPaper instance or None if parsing fails.
        """
        try: 
            # extract basic metadata 
            arxiv_id = self._get_arxiv_id(entry) 
            if not arxiv_id:
                return None 
            
            title = self._get_text(entry, "atom:title", clean_newlines = True)
            authors = self._get_authors(entry)
            abstract = self._get_text(entry, "atom:summary", clean_newlines = True)
            published = self._get_text(entry, "atom:published")
            categories = self._get_categories(entry)
            pdf_url = self.__get_pdf_url(entry)

            return ArxivPaper(
                id=arxiv_id,
                title=title,
                authors=authors,
                abstract=abstract,
                published=published,
                categories=categories,
                pdf_url=pdf_url,
            )
        except Exception as e:
            logger.error(f"Error parsing arXiv entry: {e}")
            return None
    
    def _get_text(self, element: ET.Element, path: str, clean_newline: bool = False) -> str: 
        """
        Extract text from XML element safely
        Args: 
            element (ET.Element): XML element to extract text from.
            path (str): XPath to the element containing the text.
            clean_newline (bool): Whether to clean newlines from the text.
        Returns:
            str: Extracted text or empty string if not found.

        """
        element = element.find(path, self.namespace)

        if element is None or element.text is None:
            return ""
        text = element.text.strip()
        return text.replace("\n", " ") if clean_newline else text
    
    def _get_arxiv_id(self, entry: ET.Element) -> Optional[str]:
        """
        Extract arXiv ID from entry.
        Args:
            entry (ET.Element): XML element representing a single paper entry.
        Returns:
            Optional[str]: arXiv ID or None if not found.

        """
        id_element = entry.find("arxiv:id", self.namespace)
        if id_element is None or id_element.text is None:
            return None
        return id_element.text.strip()
    
    def _get_authors(self, entry: ET.Element) -> list[str]:
        """Extract authors from entry."""
        authors = []
        for author in entry.findall("atom:author", self.namespace):
            name = author.find("atom:name", self.namespace)
            if name is not None and name.text is not None:
                authors.append(name.text.strip())
        return authors

    def _get_categories(self, entry: ET.Element) -> list[str]:
        """Extract categories from entry."""
        categories = []
        for category in entry.findall("arxiv:category", self.namespace):
            if category is not None and category.attrib.get("term") is not None:
                categories.append(category.attrib["term"].strip())
        return categories

    def _get_pdf_url(self, entry: ET.Element) -> Optional[str]:
        """Extract PDF URL from entry."""
        for link in entry.findall("atom:link", self.namespace):
            if link.get("type") == "application/pdf":
                url = link.get("href", "")
                if url.startswith("http://arxiv.org/"):
                    url = url.replace("http://arxiv.org/", "https://arxiv.org/")
                return url
        return ""

    async def download_pdf(self, paper: ArxivPaper, force_download: bool = False) -> Optional[Path]:
        """Download the PDF of a given paper.
        
        Args:
            paper (ArxivPaper): The paper whose PDF is to be downloaded.
        Returns:
            Path: The path to the downloaded PDF or none if download failed.
        """

        if not paper.pdf_url:
            logger.error(f"No PDF URL for paper {paper.arxiv_id}")
            return None
        pdf_path = self._get_pdf_path(paper.arxiv_id)

        # return cached PDF if already downloaded
        if pdf_path.exists() and not force_download:
            logger.info(f"PDF for paper {paper.arxiv_id} already downloaded at {pdf_path}")
            return pdf_path
        
        if await self._download_with_retry(paper.pdf_url, pdf_path):
            return pdf_path
        else:
            return None 
    
    def _get_pdf_path(self, arxiv_id: str) -> Path:
        """Get the file path for the PDF of a given arXiv ID."""
        safe_filename = arxiv_id.replace("/", "_") + ".pdf"
        return self.pdf_cache_dir / safe_filename # return the full path by combining cache dir and safe filename
    

    async def _download_with_retry(self, url: str, path:Path, max_retries: Optional[int] = None ) -> bool:
        """Download a file from a URL with retry logic."""

        if max_retries is None:
            max_retries = self._settings.download_max_retries

        logger.info(f"Downloading PDF from {url} ")

        await asyncio.sleep(self._settings.rate_limit_delay)

        for attempt in range(max_retries):
            try: 
                async with httpx.AsyncClient(timeout = float(self._settings.timeout_secs)) as client: 
                    async with client.stream("GET", url) as response:
                        response.raise_for_status()
                        with open(path, "wb") as f:
                            async for chunk in response.aiter_bytes():
                                f.write(chunk)
                logger.info(f"Successfully downloaded PDF to {path}")
                return True
            except Exception as e:
                if attempt < max_retries - 1: 
                    wait_time = self._settings.download_retry_delay_secs * (attempt +1 ) # method to increase wait time exponentially
                    logger.warning(f"Download failed for {url}. Retrying in {wait_time} seconds... (Attempt {attempt + 1}/{max_retries})")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"Failed to download PDF from {url} after {max_retries} attempts. Error: {e}")
                    raise PDFDownloadTimeoutError(f"Failed to download PDF from {url} after {max_retries} attempts. Error: {e}")
            except httpx.HTTPError as e:
                if attempt < max_retries - 1:
                    wait_time = self._settings.download_retry_delay_secs * (attempt +1 ) # method to increase wait time exponentially
                    logger.warning(f"Download failed for {url}. Retrying in {wait_time} seconds... (Attempt {attempt + 1}/{max_retries})")
                    await asyncio.sleep(wait_time)
                else:   
                    logger.error(f"Failed to download PDF from {url} after {max_retries} attempts. Error: {e}")
                    raise PDFDownloadException(f"Failed to download PDF from {url} after {max_retries} attempts. Error: {e}")

            except Exception as e:
                logger.error(f"Unexpected error downloading PDF from {url}: {e}")
                raise PDFDownloadException(f"Unexpected error downloading PDF from {url}: {e}")

        # cleaning up partial download 
        if path.exists():
            path.unlink()
            logger.info(f"Removed partial download at {path}")
        return False            
                