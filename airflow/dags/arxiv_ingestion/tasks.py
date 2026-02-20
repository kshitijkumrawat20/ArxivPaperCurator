import asyncio 
import logging 
import sys 
from datetime import datetime, timedelta 
from functools import lru_cache
from typing import Any, Dict, List, Optional, Union

sys.path.insert(0, "/opt/airflow") # Add Airflow home to sys.path for imports

from sqlalchemy import text 
from src.db.factory import make_database
from src.services.arxiv.factory import make_arxiv_client
from src.services.pdf_parser.factory import make_pdf_parser_service
from src.services.metadata_extractor  import make_metadata_fetcher

logger = logging.getLogger(__name__)

@lru_cache(maxsize=1)
def get_cached_services() -> tuple[Any, Any, Any, Any]: 
    """
    Get cached instances of the database, arXiv client, PDF parser, and metadata fetcher services.
    retunr: 
        Tuple containing instances of the database, arXiv client, PDF parser, and metadata fetcher services.
    """
    logger.info("Creating cached service instances")

    #  initialize core services 
    arxiv_client = make_arxiv_client()
    pdf_parser_service = make_pdf_parser_service()
    database = make_database()
    metadata_fetcher = make_metadata_fetcher(arxiv_client, pdf_parser_service)

    logger.info("Cached service instances created successfully")
    return database, arxiv_client, pdf_parser_service, metadata_fetcher

async def run_paper_ingestion_pipeline(target_data: str, max_results: int = 5, process_pdf : bool = False) -> None: 
    """
    Run the paper ingestion pipeline for a given target data (e.g., category or search query).
    Args:
        target_data: The target data to ingest (e.g., category or search query).
        max_results: The maximum number of results to ingest.
        process_pdf: Whether to process the PDF files for metadata extraction.
    """
    database, _arxiv_client, _pdf_parser , _metadata_fetcher = get_cached_services() 
    
    with database.get_session() as session: 
        return await _metadata_fetcher.fetch_and_process_paper(max_results = max_results, target_data = target_data, process_pdf = process_pdf, db_session  = session, store_to_db = True)


