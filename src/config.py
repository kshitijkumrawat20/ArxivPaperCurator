from typing import List, Union 
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict 

class DefaultSettings(BaseSettings):
    """Default settings for the application."""
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        fronzen=True, 
        env_nested_delimiter="__"
    )

class Settings(DefaultSettings):
    """Application settings."""

    app_version: str = "0.1.0"  
    debug: bool = True 
    environment: str = "development"
    service_name: str = "rag_api"

    # PostgreSQL database settings
    postgres_database_url: str = "postgresql://rag_user:rag_passward@localhost:5432/rag_db"
    postgres_echo_sql: bool = False 
    postgres_pool_size: int = 20 
    postgres_max_overflow: int = 0

    # openSearch configuration 
    opensearch_host: str = "http://localhost:9200"

    # ollama configurations 
    ollama_host: str = "http://localhost:11434"
    ollama_model: Union[str, List[str]] = Field(default = ["llama3.2:1b"])
    ollama_default_model: str = "llama3.2:1b"
    ollama_timeout : int = 300 # atleast 5 min 

    @field_validator("ollama_model", mode = "before")
    @classmethod
    def parse_ollama_model(cls, value):
        """Parse the ollama_model field to ensure it is a list of strings."""
        if isinstance(value, str):
            return [model.strip() for model in value.split(",") if model.strip()]
        return value 
    
def get_settings() -> Settings:
    """Get the application settings class instance."""
    return Settings()


