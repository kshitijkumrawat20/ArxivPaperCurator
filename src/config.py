
#Central settings object first. Everything else depends on it.

from typing import List, Union 
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict 

class DefaultSettings(BaseSettings):
    """Default settings for the application."""
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        frozen=True, 
        env_nested_delimiter="__"
    )
 # adding arxiv API client settings 

class ArxivSettings(DefaultSettings):
    """Arxiv API client settings."""
    
    base_url: str ="https://export.arxiv.org/api/query"
    namespaces: dict = Field(
        default={
            "atom": "http://www.w3.org/2005/Atom",
            "opensearch": "http://a9.com/-/spec/opensearch/1.1/",
            "arxiv": "http://arxiv.org/schemas/atom"
        }
    )
    pdf_cache_dir: str =".data/arxiv_pdfs"
    rate_limit_delay: float = 3.0 
    timeout_seconds: int = 10 
    max_results: int = 100 
    search_category: str= "cs.AI"  # Default search category for AI papers


class PDFParserSettings(DefaultSettings):
    """PDF parser settings."""
    
    max_pages: int = 30
    max_file_size_mb : int =20 
    do_ocr: bool = False 
    do_tables_structure: bool = True 



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
    ollama_model:  List[str] = Field(default = ["llama3.2:1b"])
    ollama_default_model: str = "llama3.2:1b"
    ollama_timeout : int = 300 # atleast 5 min 

    # arXiv settings
    arxiv: ArxivSettings = Field(default_factory=ArxivSettings)

    # PDF parser settings
    pdf_parser: PDFParserSettings = Field(default_factory=PDFParserSettings) 

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


#