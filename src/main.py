import logging
import os 
from contextlib import asynccontextmanager # it is used for managing the lifespan of the app means startup and shutdown events
from fastapi import FastAPI
from src.config import get_settings
from src.db.factory import make_database

from src.routers import ask, papers, ping

logging.basicConfig(
    level=logging.INFO, 
    format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s", 

)
logger = logging.getLogger(__name__) 

@asynccontextmanager
async def lifespan(app : FastAPI): 
    """
    Manage the lifespan of the FastAPI application.
    This function handles startup and shutdown events.

    """

    logger.info("Starting up the application...")

    settings = get_settings()
    app.state.settings = settings # store settings in app state for global access 
    database = make_database() 
    app.state.database = database
    logger.info("Database connected.")

    app.state.pdf_parser_service = None 
    app.state.opensearch_service = None 
    app.state.llm_service = None 
    logger.info("API ready")

    yield  # Control is handed over to the application here.

    database.teardown()
    logger.info("Shutting down the application...")


app = FastAPI(
    title="ArXiv Paper Search and Analysis API", 
    description="Personal arXiv CS.AI paper curator with RAG capabilities",
    version=os.getenv("APP_VERSION", "0.1.0"),
    lifespan=lifespan
)


# Include routers with /api/v1 prefix
app.include_router(ping.router, prefix="/api/v1")
app.include_router(papers.router, prefix="/api/v1")
app.include_router(ask.router, prefix="/api/v1")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, port = 8000, host = "0.0.0.0")
    