from functools import lru_cache
from typing import Annotated, Generator, Any
from fastapi import Depends, Request
from sqlalchemy.orm import Session 
from src.config import Settings
from src.db.interface.base import BaseDatabase


@lru_cache 
def get_settings() -> Settings:
    """Get the application settings with caching to avoid redundant loading."""
    return Settings()

def get_request_settings(request: Request) -> Settings:
    """Get setting from the request state."""
    return request.app.state.settings 

def get_database(request: Request) -> BaseDatabase:
    """Get database from the request state."""
    return request.app.state.database

def get_db_session(database: Annotated[BaseDatabase, Depends(get_database)]) -> Generator[Session, None, None]:
    """Get a database session."""
    with database.get_session() as session:
        yield session

def get_pdf_parser_service(request: Request):
    """Get PDF parser service from the request state."""
    return None

def get_opensearch_service(request: Request):
    """Get OpenSearch service from the request state."""
    return request.app.state.opensearch_service

def get_llm_service(request: Request):
    """Get LLM service from the request state."""
    return request.app.state.llm_service

SettingDep = Annotated[Settings, Depends(get_settings)]
DatabaseDep = Annotated[BaseDatabase, Depends(get_database)]
DBSessionDep = Annotated[Session, Depends(get_db_session)]
PDFParsingServiceDep = Annotated[object, Depends(get_pdf_parser_service)]
OpenSearchServiceDep = Annotated[object, Depends(get_opensearch_service)]
LLMServiceDep = Annotated[object, Depends(get_llm_service)]