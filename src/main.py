import logging 
import os 
from contextlib import asynccontextmanager 
from fastapi import FastAPI 
from src.config import get_settings
from src.db.factory import make_database
from src.routers import ask, paper, ping , search
import uvicorn
from src.services.arxiv.factory import make_arxiv_client
from src.services.pdf_parser.factory import make_pdf_parser_service
from src.services.opensearch.factory import make_opensearch_client
# setup logging 
logging.basicConfig(
    level = logging.INFO,
    format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for FastAPI application."""
    
    logger.info("Starting up the application...")

    # initalizing settings 
    settings = get_settings()
    app.state.settings = settings 

    database = make_database()
    app.state.database = database
    logger.info("Database initialized.")
    app.state.arxiv_client = make_arxiv_client()
    app.state.pdf_parser = make_pdf_parser_service()
    opensearch_client = make_opensearch_client()
    app.state.opensearch_client = opensearch_client

    # verify Opensearch connectivity and create index if needed
    if opensearch_client.create_index(force=False):
        logger.info("OpenSearch index verified/created successfully.")
        # Ensure index exists
        if opensearch_client.create_index(force=False):
            logger.info("OpenSearch index created")
        else:
            logger.info("OpenSearch index already exists")

        # Get index statistics
        stats = opensearch_client.get_index_stats()
        logger.info(f"OpenSearch ready: {stats.get('document_count', 0)} documents indexed")
    else:
        logger.warning("OpenSearch connection failed - search features will be limited")

        
    # app.state.LLM_service = None  # Placeholder for LLM service instance
    logger.info("API is ready")

    yield  # Control is returned to the application

    # clearup 
    database.teardown()
    logger.info("Database connection closed.")

app = FastAPI(
    title="RAG API",
    description="A FastAPI application for Retrieval-Augmented Generation (RAG) with health checks and service monitoring.",
    version = os.getenv("APP_VERSION", "0.1.0"),
    lifespan=lifespan,
    # root_path ="/api/v1"  # Set the root path for the API
)

app.include_router(ping.router, prefix="/api/v1")
# app.include_router(ask.router)
app.include_router(paper.router,prefix="/api/v1")
app.include_router(search.router, prefix="/api/v1")

if __name__ == "__main__":
    
    uvicorn.run(app, port=8000, host="0.0.0.0")