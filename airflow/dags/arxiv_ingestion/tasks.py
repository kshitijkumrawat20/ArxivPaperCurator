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


def setup_environment() : 
    """ 
    Setup the environment and verify the dependencies. 
    
    """
    logger.info("Setting up environment and verifying depenesdencies:")

    try: 
        database, arxiv_client, pdf_parser, metadata_fetcher = get_cached_services()
        logger.info("All services initialized successfully. Environment setup complete.")

        with database.get_session() as session:
            session.execute(text("SELECT 1"))
            logger.info("Database connection verified successfully.")
        
        logger.info(f"arxiv client intialted with id: {id(arxiv_client.base_url)}")
        logger.info(f"pdf parser service intialted with docling models.")

        return {"status": "success", "message": "Environment setup and dependency verification successful."}

    except Exception as e:
        logger.error(f"Error during environment setup: {e}")
        return {"status": "error", "message": f"Environment setup failed: {str(e)}"}
    
def fetch_daily_papers(
        **context
):
    """
    Fetch daily papers from arXiv and process them for metadata extraction and storage in the database.
    Args:
        context: Airflow context containing execution information.
    returns:
        A dictionary containing the status and message of the operation.
    """

    logger.info("Starting daily paper ingestion pipeline.")
    try:
        # calculating date range (yesterday - execution date - 1 ) # why -1 ? because we want to fetch papers from the day before yesterday to yesterday, since the execution date is usually set to the current date.
        execution_date = context["ds"] # YYYY-MM-DD format
        execution_dt = datetime.strptime(execution_date, "%Y-%m-%d")
        target_date = execution_dt - timedelta(days=1) # target date is yesterday
        target_date = target_date.strftime("%Y-%m-%d") # convert back to string format

        logger.info(f"Target date for paper ingestion: {target_date}")

        # run the ingestion pipeline
        results = asyncio.run(run_paper_ingestion_pipeline(target_data = f"submittedDate:[{target_date}0000 TO {target_date}2359]", max_results = 10, process_pdf = True))
        logger.info(f"Daily paper ingestion pipeline completed with results: {results}")

        # storing results for downstream tasks\
        context["task_instance"].xcom_push(key="fetch_results", value=results)
        return results 
    except Exception as e:
        logger.error(f"Error calculating target date: {e}")
        error_msg = f"Error during daily paper ingestion pipeline: {str(e)}"
        logger.error(error_msg)
        raise Exception(error_msg)
    

def proces_failed_task(**context): 
    """ 
    retry processing pdf that failed in the main fetch task.
    This functions: 
        - takes a list of filed papers list from main task 
        - retries processing with differnt settings 
        - reports final success or failure statistics.
    """
    logger.info("Starting retry process for failed papers.")

    try: 
        fetch_results = context["task_instance"].xcom_pull(key="fetch_results", task_ids="fetch_daily_papers")
        if not fetch_results: 
            logger.warning("No fetch results found in XCom. Nothing to retry.")
            return {"status": "warning", "message": "No fetch results found. No papers to retry."}

        logger.info(f"found {len(fetch_results.get('errors', []))} error to investigate")


        for error in fetch_results.get("errors", []): 
            # later implement the retyr logic 
            logger.info(f"Error to investigate: {error}")

        return {"status": "analyzed","error_logged": len(fetch_results.get("errors", [])), "message": f"error logged for investigation."}
    except Exception as e:
        error_message = f"Error during retry process for failed papers: {str(e)}"
        logger.error(error_message)
        raise Exception(error_message)

def create_opensearch_placeholder(**context):
    """  
    Creates placeholder entries for opensearch indexing.

    after the airlfow pipeline completion it can :
    1. Get successfully stored papers
    2. create placeholder opensearch documents.
    3. Prepare for actual indexing pipeline 
    """
    logger.info("Starting creation of OpenSearch placeholders.")

    try: 
        fetch_results = context["task_instance"].xcom_pull(key = "fetch_results", task_ids = "fetch_daily_papers")
        if not fetch_results:
            logger.warning("No fetch results found in XCom. No placeholders to create.")
            return {"status": "warning", "message": "No fetch results found. No placeholders created."}
        papers_stored = fetch_results.get("papers_stored", 0)
        logger.info(f"Creating OpenSearch placeholders for {papers_stored} papers."
        )
        placeholder_results = {
            "status": "success",
            "papers_ready_for_indexing": papers_stored,
            "message": f"Placeholders created for {papers_stored} papers."
        }
        logger.info(f"OpenSearch placeholder creation results: {placeholder_results}")
        return placeholder_results
    
    except Exception as e:
        error_message = f"Error during OpenSearch placeholder creation: {str(e)}"
        logger.error(error_message)
        raise Exception(error_message)
    
def generate_daily_report(**context):
    """
    Generate a daily processing report.

    This function:
    1. Collects results from all tasks
    2. Generates summary statistics
    3. Logs the daily report
    """
    logger.info("Generating daily processing report.")
    try: 
        fetch_results = context["task_instance"].xcom_pull(key = "fetch_results", task_ids = "fetch_daily_papers")

        failed_pdf_results = context["task_instance"].xcom_pull( task_ids = "process_failed_pdfs")

        opensearch_results = context["task_instance"].xcom_pull(task_ids = "create_opensearch_placeholders")

        report = {
            "date": context["ds"],
            "execution_time": datetime.now().isoformat(),
            "papers": {
                "fetched": fetch_results.get("papers_fetched", 0) if fetch_results else 0,
                "pdfs_downloaded": fetch_results.get("pdfs_downloaded", 0) if fetch_results else 0,
                "pdfs_parsed": fetch_results.get("pdfs_parsed", 0) if fetch_results else 0,
                "stored": fetch_results.get("papers_stored", 0) if fetch_results else 0,
            },
            "processing": {
                "processing_time_seconds": fetch_results.get("processing_time", 0) if fetch_results else 0,
                "errors": len(fetch_results.get("errors", [])) if fetch_results else 0,
                "failed_pdf_retries": failed_pdf_results.get("errors_logged", 0) if failed_pdf_results else 0,
            },
            "opensearch": {
                "placeholders_created": opensearch_results.get("papers_ready_for_indexing", 0) if opensearch_results else 0,
                "status": opensearch_results.get("status", "unknown") if opensearch_results else "unknown",
            },
        }

        logger.info("=== DAILY ARXIV PROCESSING REPORT ===")
        logger.info(f"Date: {report['date']}")
        logger.info(f"Papers fetched: {report['papers']['fetched']}")
        logger.info(f"PDFs downloaded: {report['papers']['pdfs_downloaded']}")
        logger.info(f"PDFs parsed: {report['papers']['pdfs_parsed']}")
        logger.info(f"Papers stored: {report['papers']['stored']}")
        logger.info(f"Processing time: {report['processing']['processing_time_seconds']:.1f}s")
        logger.info(f"Errors encountered: {report['processing']['errors']}")
        logger.info(f"OpenSearch placeholders: {report['opensearch']['placeholders_created']}")
        logger.info("=== END REPORT ===")

        return report

    except Exception as e:
        error_msg = f"Report generation failed: {str(e)}"
        logger.error(error_msg)
        raise Exception(error_msg)
