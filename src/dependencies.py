# Wire settings, database, session injection for FastAPI.

from functools import lru_cache 
from typing import Annotated, Generator 
from fastapi import Depends, Request 
from sqlalchemy.orm import Session 
from src.config import Settings
from src.db.interfaces.base import BaseDatabase 
from src.services.arxiv.client import ArxivClient 
from src.services.embeddings.jina_client import JinaEmbeddingsClient
from src.services.opensearch.client import OpenSearchClient 
from src.services.pdf_parser.parser import PDFParserService
from src.services.ollama.client import OllamaClient

@lru_cache() # Cache the settings instance to avoid reloading it multiple times for example during dependency injection in FastAPI.
def get_settings() -> Settings:
    """Get the application settings."""
    return Settings()

def get_request_settings(request: Request) -> Settings: 
    """Get the application settings from the request state."""
    return request.app.state.settings 

def get_database(request: Request) -> BaseDatabase: 
    """Get the database instance from the request state."""
    return request.app.state.database 

def get_db_session(database: BaseDatabase = Depends(get_database)) -> Generator[Session, None, None]:  # here None None means that the generator does not return any value when it is done.
    """Get a database session from the database instance."""
    with database.get_session() as session: 
        yield session

def get_pdf_parser(request: Request) -> PDFParserService:
    """Get the PDF parser instance from the request state."""
    return request.app.state.pdf_parser 

def get_embeddings_service(request: Request) -> JinaEmbeddingsClient:
    """Get the embeddings service instance from the request state."""
    return request.app.state.embeddings_service


def get_opensearch_client(request: Request) -> OpenSearchClient:
    """Get the OpenSearch client instance from the app state"""
    return request.app.state.opensearch_client

def get_arxiv_client(request: Request) -> ArxivClient:
    """Get the ArXiv client instance from the app state"""
    return request.app.state.arxiv_client

def get_ollama_client(request: Request) -> OllamaClient:
    """Get the Ollama client instance from the app state"""
    return request.app.state.ollama_client

# Dependency type aliases for better type hinting and readability
SettingsDep = Annotated[Settings, Depends(get_request_settings)]
DatabaseDep = Annotated[BaseDatabase, Depends(get_database )]
SessionDep = Annotated[Session, Depends(get_db_session)]
OpenSearchDep = Annotated[OpenSearchClient, Depends(get_opensearch_client)]
ArxivDep = Annotated[ArxivClient, Depends(get_arxiv_client)]    
PDFParserDep = Annotated[PDFParserService, Depends(get_pdf_parser)]
EmbeddingsDep = Annotated[JinaEmbeddingsClient, Depends(get_embeddings_service)]
OllamaDep = Annotated[OllamaClient, Depends(get_ollama_client)]