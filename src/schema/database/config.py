from pydantic_settings import BaseSettings
from typing import Optional
from pydantic import Field

class PostgresSQLSettings(BaseSettings):
    """Settings for PostgreSQL database connection."""

    database_url: str = Field(default = "postgresql://rag_user:rag_passward@localhost:5432/rag_db", description = "Database URL for PostgreSQL connection.")

    echo_sql: bool = Field(default = False, description = "Flag to enable SQL query logging.")

    pool_size: int = Field(default=0, description="The size of the database connection pool. Default is 0, which means no limit.")

    max_overflow: int = Field(default=0, description="The maximum number of connections that can be created after the pool reaches its size limit. Default is 10.")

    class Config: 
        env_prefix = "POSTGRES_" # Prefix for environment variables related to PostgreSQL settings.