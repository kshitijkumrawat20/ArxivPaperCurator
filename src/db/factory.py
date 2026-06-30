# Create the DB object from app settings.

from src.config import Settings, get_settings
from src.db.interfaces.base import BaseDatabase 
from src.db.interfaces.postgresql import PostgresSQLDatabase, PostgresSQLSettings

def make_database(settings: Settings | None = None) -> BaseDatabase:
    """
    Factory function to create a database instance.

    RETURN: 
        BaseDatabase: An instance of the database implementation (PostgreSQL in this case).
    """

    # Reuse settings initialized by the application when provided, while retaining
    # a no-argument form for callers that need the default environment settings.
    settings = settings or get_settings()

    # creating PostgreSQL config from settings 

    config = PostgresSQLSettings(
        database_url = settings.postgres_database_url,
        echo_sql = settings.postgres_echo_sql,
        pool_size = settings.postgres_pool_size, 
        max_overflow = settings.postgres_max_overflow  
    )
    database = PostgresSQLDatabase(config) # Create an instance of the PostgreSQL database implementation with the provided configuration.
    database.startup() # Initialize the database connection and create tables if they do not exist.
    return database

