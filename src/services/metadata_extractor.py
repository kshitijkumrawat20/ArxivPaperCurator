import asyncio 
import logging 
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Union 
from dateutil import parser as date_parser 
from sqlalchemy.orm import Session 
from src.exceptions import MetadataFetchingException, PipelineException
from src.repositories.paper import PaperRepository
from src.schemas.arxiv.paper import ArxivPaper, PaperCreate
from src.schemas.pdf_parser.models import PdfContent, ParserType
from src.services.arxiv.client import ArxivClient
from src.services.pdf_parser.parser import PDFParserService
logger = logging.getLogger(__name__)

class MetadataFetcher:
    """
    Services for fetching arxiv papers with PDF processing and database storage.
    
    This service orchestrates the complete pipeling:
    1. Fetching paper metadata from arXiv API.
    2. Download PDF with caching.
    3. Parse PDFs with Docling 
    4. Store complete paper data in the PostgreSQL database.
    """

    def __init__(
        self,
        arxiv_client: ArxivClient,
        pdf_parser: PDFParserService, 
        pdf_cache_dir: Optional[Path] = None,
        max_concurrent_downloads: int = 5, 
        max_concurrent_parsing: int = 3 

    ):
        """
        Initialize the MetadataFetcher with necessary services and configurations.
        Args:
            arxiv_client (ArxivClient): An instance of the ArxivClient for fetching metadata and downloading PDFs.
            pdf_parser (PDFParserService): An instance of the PDFParserService for parsing PDF content.
            pdf_cache_dir (Optional[Path]): Directory path for caching downloaded PDFs. If None, caching is disabled.
            max_concurrent_downloads (int): Maximum number of concurrent PDF downloads.
            max_concurrent_parsing (int): Maximum number of concurrent PDF parsing operations.
        
        """
        self.arxiv_client = arxiv_client
        self.pdf_parser = pdf_parser
        self.pdf_cache_dir = pdf_cache_dir or self.arxiv_client.pdf_cache_dir
        self.max_concurrent_downloads = max_concurrent_downloads
        self.max_concurrent_parsing = max_concurrent_parsing

    async def fetch_and_process_paper(
            self,
            max_results: Optional[int] = None,
            from_date: Optional[str] = None,
            process_pdf: bool = True,
            store_to_db: bool = True,
            db_session: Optional[Session] = None,
            to_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Fetch papers from arXiv, process PDFs, and optionally store results in the database.
        Args:
            max_results (Optional[int]): Maximum number of papers to fetch. If None, fetches all available papers.
            from_date (Optional[str]): Start date for fetching papers (inclusive). Format: 'YYYY-MM-DD'.
            process_pdf (bool): Whether to download and parse PDFs. If False, only metadata is fetched.
            store_to_db (bool): Whether to store the fetched and processed data in the database. Requires db_session if True.
            db_session (Optional[Session]): SQLAlchemy session for database operations. Required if store_to_db is True.
            to_date (Optional[str]): End date for fetching papers (inclusive). Format: 'YYYY-MM-DD'.
        
        Returns:
            Dict[str, Any]: A dictionary containing the results of the operation, including counts of processed papers and any errors encountered.
        
        Raises:
            MetadataFetchingException: If there is an error during metadata fetching or processing.
            PipelineException: If there is a critical error in the pipeline that prevents completion.
        """
        results = {
            "papers_fetched": 0,
            "papers_downloaded": 0,
            "pdf_parsed": 0,
            "papers_stored": 0,
            "errors": [],
            "processing_time": 0.0
        }
        start_time = datetime.now()
        try: 
            # step: 1 fetch the paper metadata from the arxiv API client 
            papers = await self.arxiv_client.fetch_papers(
                max_results=max_results,
                from_date=from_date,
                to_date=to_date, 
                sort_by="submittedDate",
                sort_order="descending"

            )
            results["papers_fetched"] = len(papers)
            logger.info(f"Fetched {len(papers)} papers from arXiv API.")
            if not papers:
                logger.warning("No papers found for the given criteria.")
                return results

            # step: 2 : Process the pdf if requested 
            pdf_results  = {}
            if process_pdf: 
                pdf_results = await self._process_pdf_batch(papers)
            results["pdf_downloaded"] = pdf_results["downloaded"]
            results["pdf_parsed"] = pdf_results["parsed"]
            results["errors"].extend(pdf_results["errors"])

            # step: 3 store to database if requested
            if store_to_db and db_session :
                logger.info("Storing papers to database...")
                stored_count = self._store_papers_to_db(papers, pdf_results.get("parsed_papers", {}), db_session)

                results["papers_stored"] = stored_count
            elif store_to_db:
                logging.warning("Database storage but no session provided for storage")
                results["errors"].append("Database storage requested but no session provided.")
            
            # calculate total processing time 
            processing_time = (datetime.now() - start_time).total_seconds()
            results["processing_time"] = processing_time

            ## logging summary 
            logger.info(f"Pipeline Completed in {processing_time:.2f}s: Fetched: {results['papers_fetched']}, Downloaded: {results['pdf_downloaded']}, Parsed: {results['pdf_parsed']}, Stored: {results['papers_stored']}, Errors: {len(results['errors'])}")

            if results["errors"]:
                logger.warning("Error summary:")
                for i, error in enumerate(results["errors"][:5], 1):
                    logger.warning(f"{i}. {error}")
                if len(results["errors"]) > 5:
                    logger.warning(f"... and {len(results['errors']) - 5} more errors.")
            return results
        except Exception as e:
            logger.error(f"Critical error in metadata fetching pipeline: {str(e)}")
            logger.error(f"Pipeline execution: {results}.")
            results["errors"].append(f"Critical pipeline error: {str(e)}")
            raise PipelineException(f"Critical error in metadata fetching pipeline: {str(e)}")


    async def _process_pdf_batch(self, papers: List[ArxivPaper]) -> Dict[str, Any]:
            """
            Process a batch of papers: download and parse PDFs concurrently.
            Uses overlapping download + parse pipeline for efficiency.
            Downloads happen concurrently (up to max_concurrent_downloads) and parsing happens concurrently (up to max_concurrent_parsing) as soon as PDFs are downloaded.
            Args:
                papers: List of ArxivPaper metadata objects.
            
            Returns:
                A dictionary with counts of downloaded and parsed PDFs, parsed paper data, and any errors encountered.
            """

            results = {
                "downloaded": 0,
                "parsed": 0,
                "parsed_papers": {}, # key: arxiv_id, value: parsed content
                "errors": [],
                "download_failures": [],
                "parse_failures": []
            }
            logger.info(f"Starting PDF processing for {len(papers)} papers with max {self.max_concurrent_downloads} concurrent downloads and max {self.max_concurrent_parsing} concurrent parses.")
            # semaphores to limit concurrency 
            download_semaphore = asyncio.Semaphore(self.max_concurrent_downloads)
            parse_semaphore = asyncio.Semaphore(self.max_concurrent_parsing)

            # start all download + Parse pipelines concurrently
            pipeline_tasks = [
                self._download_and_parse_pipeline(
                    paper, 
                    download_semaphore, # download limiter
                    parse_semaphore # parse limiter
                )
                for paper in papers
            ] # it will return a list of coroutine objects for each paper for example [coroutine1, coroutine2, coroutine3, ...] where each coroutine represents the download and parse pipeline for a specific paper
            # wait for all pipelines to complete
            pipeline = await asyncio.gather(*pipeline_tasks, return_exceptions=True) # gather will run all the coroutines concurrently and return a list of results in the same order as the input list. If return_exceptions=True, it will capture exceptions as part of the results instead of raising them immediately.

            # process results with detailed error tracking 
            for paper, result in zip(papers, pipeline): # zip object yields n length tuples of (paper, result) for example (paper1, result1), (paper2, result2) ...
                if isinstance(result, Exception): # ifinstance checks if result is an exception object, which means the pipeline for that paper failed with an error
                    error_msg = f"Pipeline error for paper {paper.arxiv_id}: {str(result)}"
                    logger.error(error_msg)
                    results["errors"].append(error_msg)
                elif result:
                    download_success, parsed_paper = result
                    if download_success:
                        results["downloaded"] += 1
                        if parsed_paper:
                            results["parsed"] += 1
                            results["parsed_papers"][paper.arxiv_id] = parsed_paper
                        else: 
                            results["parse_failures"].append(paper.arxiv_id)
                    else:
                        results["download_failures"].append(paper.arxiv_id)
                else:

                    results["download_failures"].append(paper.arxiv_id)

            logger.info(f"PDF processing: {results['downloaded']} downloaded, {len(results['parse_failures'])} parse failures, {len(results['download_failures'])} download failures.")

            if results["download_failures"]:
                logger.warning(f"Download failures for {len(results['download_failures'])}")

            if results["parse_failures"]:
                logger.warning(f"Parse failures for {len(results['parse_failures'])}")
            
            ## adding specific failure info to general error list for backward compatibility and summary reporting
            if results["download_failures"]:
                results["errors"].extend([f"Download failure for paper {arxiv_id}" for arxiv_id in results["download_failures"]])
            if results["parse_failures"]:
                results["errors"].extend([f"Parse failure for paper {arxiv_id}" for arxiv_id in results["parse_failures"]])
            
            return results
