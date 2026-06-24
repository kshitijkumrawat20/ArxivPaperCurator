import logging 
from contextlib import contextmanager 
from typing import Generator, Optional
from unittest.mock import Base 
from pydantic import Field, BaseModel 
from pydantic_settings import BaseSettings
from sqlalchemy import create_engine, inspect, text 
from sqlalchemy.engine import Engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session, sessionmaker 
# from src.db.interfaces.base import BaseDatabase

logger = logging.getLogger(__name__)

class PostgresSQLSettings(BaseSettings):
    """Settings for PostgreSQL database connection."""

    database_url: str = Field(default = "postgresql://rag_user:rag_passward@localhost:5432/rag_db", description = "Database URL for PostgreSQL connection.")

    echo_sql: bool = Field(default = False, description = "Flag to enable SQL query logging.")

    pool_size: int = Field(default=0, description="The size of the database connection pool. Default is 0, which means no limit.")

    max_overflow: int = Field(default=0, description="The maximum number of connections that can be created after the pool reaches its size limit. Default is 10.")

    class Config: 
        env_prefix = "POSTGRES_" # Prefix for environment variables related to PostgreSQL settings.

Base = declarative_base() # Base class for SQLAlchemy models. means it will be used to define the structure of the database tables and their relationships.

class PostgresSQLDatabase(BaseDatabase):
    """PostgreSQL database implementation."""

    def __init__(self, config: PostgresSQLSettings):
        self.config = config
        self.engine: Optional[Engine] = None # engine is optional because it will be initialized later in the connect method.
        self.session_factory: Optional[sessionmaker] = None # session_factory is optional because it will be initialized later in the connect method.

    def startup(self) -> None: 
        """Initialize the database connection and create tables."""
        try: 
            # log connection attempt 
            logger.info(f"Connecting to  PostgresSQL database at {self.config.database_url.split('@')[1] if '@' in self.config.database_url else self.config.database_url} ...")

            self.engine = create_engine(self.config.database_url, echo = self.config.echo_sql, pool_size = self.config.pool_size, max_overflow=self.config.max_overflow) # Create the SQLAlchemy engine for PostgreSQL connection.

            self.session_factory = sessionmaker(bind = self.engine, expire_on_commit = False) # Create a session factory for managing database sessions. and expire_on_commit=False means that the session will not expire objects after a commit, allowing them to be accessed after the transaction is committed.

            # testing the connecting 
            assert self.engine is not None, "Engine is not initialized." # assert here means that if the engine is not initialized, it will raise an AssertionError with the message "Engine is not initialized."
            with self.engine.connect() as conn: 
                conn.execute(text("SELECT 1")) # Execute a simple query to test the connection. If the query fails, it will raise an exception.

                logger.info("PostgreSQL database connection established successfully.") # log successful connection

            # check which tables exist in the database before creating new tables 

            inspector = inspect(self.engine) # Create an inspector to check the existing tables in the database.
            existing_tables = inspector.get_table_names() # Get the list of existing tables in the database.

            # creating tables if not exist in the database 
            Base.metadata.create_all(bind = self.engine) # Create all tables defined in the SQLAlchemy models if they do not already exist in the database.Base is the declarative base class that contains the metadata for all the models.

            # check if tany tables is created 
            updated_tables = inspector.get_table_names() # Get the list of tables after attempting to create them.
            new_tables = set(updated_tables) - set(existing_tables) # Determine which tables were newly created by comparing the existing and updated table lists.
            if new_tables:
                logger.info(f"New tables created in the PostgreSQL database: {', '.join(new_tables)}") # Log the names of any newly created tables.
            else:
                logger.info("No new tables were created in the PostgreSQL database.") # Log that no new tables were created.
            logger.info("PostgreSQL database startup completed successfully.") # Log that the database startup process has completed successfully.
            assert self.engine is not None, "Engine is not initialized after startup." # assert here means that if the engine is not initialized after startup, it will raise an AssertionError with the message "Engine is not initialized after startup."

            logger.info("Database: {self.engine.url.database}")
            logger.info(f"Total tables: {', '.join(updated_tables)}") # Log the total number of tables in the database after startup.

        except Exception as e:
            logger.error(f"Failed to initialize PostgreSQL database connection: {e}") 
            raise 
    
    def teardown(self) -> None: 
        """Close the database connection and clean up resources."""
        if self.engine: 
            self.engine.dispose() # Dispose of the SQLAlchemy engine, closing all connections in the pool.
            logger.info("PostgreSQL database connection closed.") # Log that the database connection has been
    
    @contextmanager
    def get_session(self) -> Generator[Session, None, None]: # 
        """Get a database session"""
        if not self.session_factory: 
            raise RuntimeError("Session factory is not initialized. Call startup() first.") 

        session = self.session_factory()
        try: 
            yield session # Yield the session to the caller, allowing them to use it within a context manager.
        except Exception as e:
            session.rollback() # Roll back the session in case of an exception to avoid leaving the session in an inconsistent state.
            logger.error(f"Session rollback due to error: {e}") # Log the error that caused the rollback.
            raise
        finally:
            session.close() # Close the session to release database resources.
            logger.info("Database session closed.") # Log that the database session has been closed.
            
