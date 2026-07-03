# Wire settings, database, session injection for FastAPI.

from functools import lru_cache 
from typing import Annotated, Generator 
from fastapi import Depends, Request 
from sqlalchemy.orm import Session 
from src.config import Settings
from src.db.interfaces.base import BaseDatabase 

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

# def get_pdf_parser(request: Request):  # Replace 'Any' with the actual type of the PDF parser instance
#     """Get the PDF parser instance from the request state."""
#     return request.app.state.pdf_parser 

# def get_opensearch_service(request: Request): 
#     """Get the OpenSearch service instance from the app state"""
#     return getattr(request.app.state, "opensearch_service", None)  # Return None if the attribute does not exist

# def get_LLM_service(request: Request): 
#     """Get the LLM service instance from the app state"""
#     return None 

# Dependency type aliases for better type hinting and readability
SettingsDep = Annotated[Settings, Depends(get_request_settings)]
DatabaseDep = Annotated[BaseDatabase, Depends(get_database )]
SessionDep = Annotated[Session, Depends(get_db_session)]
# PDFParserDep = Annotated[object, Depends(get_pdf_parser)]  # Replace 'object' with the actual type of the PDF parser instance
# OpenSearchServiceDep = Annotated[object, Depends(get_opensearch_service)]  # Replace 'object' with the actual type of the OpenSearch service instance
# LLMServiceDep = Annotated[object, Depends(get_LLM_service)]  # Replace 'object' with the actual type of the LLM service instance