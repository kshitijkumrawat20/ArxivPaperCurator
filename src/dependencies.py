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

SettingDep = Annotated[Settings, Depends(get_settings)]
DatabaseDep = Annotated[BaseDatabase, Depends(get_database)]
DBSessionDep = Annotated[Session, Depends(get_db_session)]
