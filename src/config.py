
#Central settings object first. Everything else depends on it.

from typing import List, Literal
import os 
from pathlib import Path 
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict 

PROJECT_ROOT = Path(__file__).parent.parent
ENV_FILE_PATH = PROJECT_ROOT / ".env"

class BaseConfigSettings(BaseSettings):
    """Default settings for the application."""
    model_config = SettingsConfigDict(
        env_file=[".env", str(ENV_FILE_PATH)],
        extra="ignore",
        frozen=True, 
        env_nested_delimiter="__",
        case_sensitive=False,
    )
 # adding arxiv API client settings 

class ArxivSettings(BaseConfigSettings):
    """Arxiv API client settings."""

    model_config = SettingsConfigDict(
        env_file=[".env", str(ENV_FILE_PATH)],
        env_prefix="ARXIV__",
        extra="ignore",
        frozen=True,
        case_sensitive=False,
    )
    
    base_url: str ="https://export.arxiv.org/api/query"
    pdf_cache_dir: str =".data/arxiv_pdfs"
    rate_limit_delay: float = 3.0 
    timeout_seconds: int = 30 
    max_results: int = 15 
    search_category: str= "cs.AI"  # Default search category for AI papers
    download_max_retries: int = 3
    download_retry_delay: float = 5.0  # Delay between retries in seconds
    max_concurrent_downloads: int = 5  # Maximum number of concurrent downloads
    max_concurrent_parsing: int = 1  

    namespaces: dict = Field(
        default={
            "atom": "http://www.w3.org/2005/Atom",
            "opensearch": "http://a9.com/-/spec/opensearch/1.1/",
            "arxiv": "http://arxiv.org/schemas/atom"
        }
    )

    @field_validator("pdf_cache_dir")
    @classmethod 
    def validate_pdf_cache_dir(cls, v: str) -> str:
        """Ensure the PDF cache directory exists."""
        os.makedirs(v, exist_ok=True)
        return v
    

class PDFParserSettings(BaseConfigSettings):
    """PDF parser settings."""
    model_config = SettingsConfigDict(
        env_file=[".env", str(ENV_FILE_PATH)],
        env_prefix="PDF_PARSER__",
        extra="ignore",
        frozen=True,
        case_sensitive=False,
    )
    max_pages: int = 50
    max_file_size_mb : int =50 
    do_ocr: bool = False 
    do_tables_structure: bool = True 

class ChunkingSettings(BaseConfigSettings):
    model_config = SettingsConfigDict(
        env_file = [".env", str(ENV_FILE_PATH)],
        env_prefix = "CHUNKING__",
        extra = "ignore",
        frozen = True,
        case_sensitive = False,
    )
    chunk_size: int = 600
    overlap_size: int = 100
    min_chunk_size: int = 100
    section_based : bool = True # Use section based chunking when availables    

class OpenSearchSettings(BaseConfigSettings):
    """OpenSearch settings."""
    model_config = SettingsConfigDict(
        env_file=[".env", str(ENV_FILE_PATH)],
        env_prefix="OPENSEARCH__",
        extra="ignore",
        frozen=True,
        case_sensitive=False,
    )
    host: str = "http://localhost:9200"
    index_name: str = "arxiv-papers"
    chunk_index_suffix : str = "chunks" # create single hybrid index: {index_name}-{chunk_index_suffix}
    max_text_size: int = 1000000

    # Vector search settings 
    vector_dimension: int = 1024
    vector_space_type: str = "cosinesimil" 

    # Hybrid Search settings 
    rrf_pipeline_name : str = "hybrid-rrf-pipeline" # RRf here is the reciprocal rank fusion pipeline name in OpenSearch
    hybrid_search_size_multiplier: int = 3 # multiplier for the number of results to retrieve for hybrid search (e.g., if size=10 and multiplier=3, then 30 results will be retrieved)
class Settings(BaseConfigSettings):
    """Application settings."""
    
    app_version: str = "0.1.0"  
    debug: bool = True 
    environment: Literal["development","staging","production"] = "development"
    service_name: str = "rag_api"

    # PostgreSQL database settings
    postgres_database_url: str = "postgresql://rag_user:rag_passward@localhost:5432/rag_db"
    postgres_echo_sql: bool = False 
    postgres_pool_size: int = 20 
    postgres_max_overflow: int = 0

    # ollama configurations 
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "llama3.2:1b"
    ollama_timeout : int = 300 # atleast 5 min 

    # Jina Ai embedding configurations 
    jina_api_key: str = "YOUR_JINA_API_KEY"

    # arXiv settings
    arxiv: ArxivSettings = Field(default_factory=ArxivSettings)

    # PDF parser settings
    pdf_parser: PDFParserSettings = Field(default_factory=PDFParserSettings) 

    chunking: ChunkingSettings = Field(default_factory=ChunkingSettings)

    # OpenSearch settings
    opensearch: OpenSearchSettings = Field(default_factory=OpenSearchSettings)

    @field_validator("postgres_database_url")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        if not (v.startswith("postgresql://") or v.startswith("postgresql+psycopg2://")):
            raise ValueError("Invalid PostgreSQL database URL. It must start with 'postgresql://' or 'postgresql+psycopg2://'.")
        return v

    # @field_validator("ollama_model")
    # @classmethod
    # def parse_ollama_model(cls, value):
    #     """Parse the ollama_model field to ensure it is a list of strings."""
    #     if isinstance(value, str):
    #         return [model.strip() for model in value.split(",") if model.strip()]
    #     return value 
    
def get_settings() -> Settings:
    """Get the application settings class instance."""
    return Settings()


#