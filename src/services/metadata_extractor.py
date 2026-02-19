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
from src.schemas.pdf_parser.models import ParsedPaper, ArxivMetadata
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
                    download_success, parsed_paper = results
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
    
    async def _download_and_parse_pipeline(
        self, 
        paper: ArxivPaper,
        download_semaphore: asyncio.Semaphore,
        parse_semaphore: asyncio.Semaphore
    ) -> tuple:
        """
        Complete pipeline for download and parsing for a single paper with true parallelism between download and parse steps.
        returns:
            tuple: (download_success: bool, parsed_paper: Optional[ParsedPaper])
        """
        
        download_success = False
        parsed_paper = None

        try: 
            async with download_semaphore: # Download PDF with download concurrency control
                logger.info(f"Starting download for paper {paper.arxiv_id} with download semaphore control.")
                pdf_path = await self.arxiv_client.download_pdf(paper)
                if pdf_path:
                    download_success = True
                    logger.info(f"Downloaded PDF for paper {paper.arxiv_id} to {pdf_path}.")
                else:
                    logger.warning(f"Failed to download PDF for paper {paper.arxiv_id}.")
                    return (False, None) # early return on download failure
            async with parse_semaphore: # Parse PDF with parse concurrency control
                pdf_content = await self.pdf_parser.parse_pdf(pdf_path)
                if pdf_content:
                    logger.info(f"Parsed PDF for paper {paper.arxiv_id} successfully.")
                else:
                    logger.warning(f"Failed to parse PDF for paper {paper.arxiv_id}.")
                if pdf_content:
                    arxiv_metadata = ArxivMetadata(
                        title=paper.title,
                        authors=paper.authors,
                        abstract=paper.abstract,
                        arxiv_id=paper.arxiv_id,
                        categories=paper.categories,
                        published_date=paper.published_date,
                        pdf_url=paper.pdf_url
                    )

                    parsed_paper = ParsedPaper(
                        arxiv_metadata=arxiv_metadata,
                        pdf_content=pdf_content
                    )
                    logger.debug(f"Parse completed: {paper.arxiv_id} - {len(pdf_content.raw_text)} characters of content extracted.")
                else:
                    logger.warning(f"No content extracted from PDF for paper {paper.arxiv_id}.")
        except Exception as e:
            logger.error(f"Error in download and parse pipeline for paper {paper.arxiv_id}: {str(e)}")
            raise MetadataFetchingException(f"Error in download and parse pipeline for paper {paper.arxiv_id}: {str(e)}") 
        return (download_success, parsed_paper)
        
                
    def serialize_parsed_content(self, parsed_paper: ParsedPaper) -> Dict[str, Any]:
        """
        Serialize the parsed paper content into a dictionary format suitable for database storage.
        Args:
            parsed_paper (ParsedPaper): The parsed paper object containing metadata and PDF content.
        Returns:
            Dict[str, Any]: A dictionary representation of the parsed paper ready for database insertion.
        """
        try:
            pdf_content = parsed_paper.pdf_content

            # serialize sections with content and metadata
            sections = [{"title": section.title, "content": section.content} for section in pdf_content.sections]
            # serialize reference 
            references = list(pdf_content.references)
            return {
                "raw_text" : pdf_content.raw_text,
                "sections": sections,
                "references": references,
                "parser_used": pdf_content.parser_used.value,
                "parser_metadata": pdf_content.metadata or {},
                "pdf_processed" : True,
                "pdf_processing_date" : datetime.now()
            }
        except Exception as e:
            logger.error(f"Error serializing parsed content for paper {parsed_paper.arxiv_metadata.arxiv_id}: {str(e)}")
            return {"pdf_processed": False, "parsed_metadata": {"error": str(e)}}
    
    def _store_papers_to_db(self, papers: List[ArxivPaper], parsed_papers: Dict[str, ParsedPaper], db_session: Session) -> int:
        """ 
        Store the fetched and processed papers into the database using the provided session.
        Args: 
            papers: List of ArxivPaper metadata objects.
            parsed_papers: Dictionary of parsed paper content keyed by arxiv_id.
            db_session: SQLAlchemy session for database operations.
        Returns:
            int: The number of papers successfully stored in the database.
        """
        paper_repo = PaperRepository(db_session)
        stored_count = 0
        for paper in papers:
            try:
                parsed_paper  = parsed_papers.get(paper.arxiv_id)

                # Base paper data 
                published_date = (date_parser.parse(paper.published_date) if isinstance(paper.published_date, str) else paper.published_date)
                paper_data = {
                    "arxiv_id": paper.arxiv_id,
                    "title": paper.title,
                    "authors": paper.authors,
                    "abstract": paper.abstract,
                    "categories": paper.categories,
                    "published_date": published_date,
                    "pdf_url": paper.pdf_url
                }
                
                # add parsed content if available
                if parsed_paper:
                    parsed_content = self.serialize_parsed_content(parsed_paper)
                    paper_data.update(parsed_content)
                    logger.debug(
                        f"storing paper {paper.arxiv_id} with parsed content: ({len(parsed_content.get('raw_text', '')) if parsed_content.get('raw_text') else 0} characters)"
                    )
                else:
                    paper_data.update(
                        {
                            "pdf_processed": False,
                            "parser_metadata": {"note": "pdf processing not available or failed."}
                        }
                    )
                    logger.debug(f"storing paper {paper.arxiv_id} without parsed content with metdata only.")
                
                paper_create = PaperCreate(**paper_data)
                stored_paper = paper_repo.upsert(paper_create)

                if stored_paper:
                    stored_count += 1
                    content_info = "with parsed content" if parsed_paper else "with metadata only"
                    logger.info(f"Stored paper {paper.arxiv_id} in database with ID {stored_paper.id} {content_info}.")
            except Exception as e:
                logger.error(f"Error storing paper {paper.arxiv_id} to database: {str(e)}")
            
        try: 
            db_session.commit()
            logger.info(f"Database commit successful for {stored_count} papers.")
        except Exception as e:
            logger.error(f"Database commit failed after storing papers: {str(e)}")
            db_session.rollback()
            stored_count = 0 # reset count if commit fails
        return stored_count

def make_metadata_fetcher(
    arxiv_client: ArxivClient,
    pdf_parser: PDFParserService,
    pdf_cache_dir: Optional[Path] = None,
) -> MetadataFetcher:
    """
    Factory function to create MetadataFetcher instance optimized for production.

    Configured for typical production workloads (100 papers/day):
    - 5 concurrent downloads (I/O bound, can handle more)
    - 3 concurrent parsing operations (CPU intensive, use fewer)
    - Async pipeline for optimal resource utilization

    Args:
        arxiv_client: Configured ArxivClient
        pdf_parser: Configured PDFParserService (singleton with model caching)
        pdf_cache_dir: Optional PDF cache directory

    Returns:
        MetadataFetcher instance optimized for production
    """
    return MetadataFetcher(
        arxiv_client=arxiv_client,
        pdf_parser=pdf_parser,
        pdf_cache_dir=pdf_cache_dir,
        max_concurrent_downloads=5,
        max_concurrent_parsing=1,
    )
                


