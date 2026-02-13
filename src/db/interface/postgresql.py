import logging
from contextlib import contextmanager # it is used to create context managers for resource management
from typing import Generator, Optional  # it is used for type hinting of generator functions means it will generate a sequence of values.
from sqlalchemy import create_engine, text, inspect
from pydantic import Field 
from sqlalchemy.engine import Engine  # it is used to represent the core interface to the database
from pydantic_settings import BaseSettings # it is used to create settings classes with validation and parsing capabilities
from sqlalchemy.ext.declarative import declarative_base # it is used to create a base class for declarative class definitions
from sqlalchemy.orm import sessionmaker, Session # it is used to create a session factory and manage database sessions
from src.db.interface.base import BaseDatabase # import the abstract base class for database interactions

logger = logging.getLogger(__name__)

class PostgresqlSettings(BaseSettings): 
    """
    Configuration settings for PostgreSQL database connection.
     
    """

    database_url : str = Field(
        default = "postgresql+psycopg2://rag_user:rag_password@localhost:5432/rag_db",
        description= "Database connection URL for PostgreSQL."
    )

    echo_sql : bool = Field(
        default= False,
        description= "Flag to enable SQL query logging."
    )
    pool_size: int = Field(
        default= 20, 
        description= "The size of the database connection pool."
    )
    max_overflow: int = Field(
        default= 0,
        description= "The maximum overflow size of the database connection pool."
    )
    class Config:
        env_prefix = "POSTGRESQL_" 

Base = declarative_base() # Make a base class in SQLAlchemy so that we can define the tables in database tables as python classes.

class PostgreSQLDatabase(BaseDatabase):
    """PostgreSQL database implementation"""

    def __init__(self, config: PostgresqlSettings):
        self.config = config
        self.engine: Optional[Engine] = None
        self.session_factory: Optional[sessionmaker] = None 

    def startup(self) -> None:
        """Initiazlize the database connection """
        try: 
            logger.info(
                f"Starting up PostgreSQL database with URL: {self.config.database_url}"
            )

            self.engine = create_engine(
                self.config.database_url,
                echo = self.config.echo_sql,
                pool_size = self.config.pool_size,
                max_overflow = self.config.max_overflow,
                pool_pre_ping = True # to check if the connection is alive before using it
            )
            self.session_factory = sessionmaker(
                bind = self.engine, 
                expire_on_commit= False # it is used because we want to access the data after the session is committed.
            )

            # test the connection 
            assert self.engine is not None
            with self.engine.connect() as conn: 
                conn.execute(text("SELECT 1"))
                logger.info("PostgreSQL database connection established successfully.")

            # check the tables if they dont exist
            inspector = inspect(self.engine)
            existing_tables = inspector.get_table_names()

            # create tabls if they dont exist 
            Base.metadata.create_all(bind = self.engine)

            # checking if any new tables were created
            updated_tables = inspector.get_table_names()
            new_tables = set(updated_tables) - set(existing_tables)

            if new_tables:
                logger.info(f"Created new tables in the database: {new_tables}")
            else: 
                logger.info("No new tables were created in the database.")
            
            logger.info("PostgreSQL databse connection is intialized successfully.")

            assert self.engine is not None
            logger.info(f"Database: {self.engine.url.database}" )
            logger.info(f"Total Tables: {', '.join(updated_tables) if updated_tables else 'None'}")
            logger.info("Database connection is established successfully.")

        except Exception as e:
            logger.error(f"Error during PostgreSQL database startup: {e}")
            raise

    def teardown(self) -> None:
        """Close the database connection"""
        if self.engine: 
            self.engine.dispose() # Dispose of the engine and its connection pool
            logger.info("PostgreSQL database connection closed successfully.")

    @contextmanager # it is used for providing a context manager for database sessions
    def get_session(self) -> Generator[Session, None, None]: # here the generator is a type hint that indicates that this function will yield Session objects
        """Provide a database session for executing queries."""
        if not self.session_factory:
            raise RuntimeError("Database session factory is not initialized. Call startup() first.")
        session = self.session_factory()

        try: 
            yield session
        except Exception as e:
            session.rollback() # rollback the session in case of exception
            logger.error(f"Session rollback because of exception: {e}")
        finally:
            session.close()
            logger.debug("Session closed successfully.")

            

