from src.config import get_settings

from src.db.interface.base import BaseDatabase
from src.db.interface.postgresql import PostgreSQLDatabase, PostgresqlSettings

def make_database() -> BaseDatabase:
    """
    Factory function to create a database instance based on configuration settings.
    Returns:
    Factory function to create a database instance based on configuration settings.
    """

    settings = get_settings()
    config = PostgresqlSettings(
        database_url = settings.postgres_database_url, 
        echo_sql = settings.postgres_echo_sql,
        pool_size = settings.postgres_pool_size,
        max_overflow = settings.postgres_max_overflow
    )
    database = PostgreSQLDatabase(config = config)
    database.startup()
    return database


