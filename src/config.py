import os 
from pathlib import Path 
from typing import List, Literal, Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

## Base class for settings, allowing values to be overridden by environment variables. This is useful in production for secrets you do not wish to save in code, it plays nicely with docker(-compose), Heroku and any 12 factor app design.

PROJECT_ROOT = Path(__file__).parent.parent
ENV_FILE_PATH  = PROJECT_ROOT / ".env"

class BaseConfigSettings(BaseSettings):
    """Base configuration class for the application settings."""
    model_config = SettingsConfigDict(
        env_file = [".env", str(ENV_FILE_PATH)],
        extra="ignore", # Ignore extra environment variables not defined in the model
        frozen = True, # Make the settings immutable after creation
        env_nested_delimiter= "__", # Support nested environment variables using double underscores
        case_sensitive=False # Environment variable names are case insensitive
    )

class ArxivSettings(BaseConfigSettings): 
    model_config = SettingsConfigDict(
        env_file=[".env", str(ENV_FILE_PATH)],
        extra="ignore",
        frozen=True,
        env_prefix="ARXIV_",
        case_sensitive=False
    )
    base_url: str = "https://export.arxiv.org/api/query"
    pdf_cache_dir: str = "./data/arxiv_pdfs" 
    rate_limit_delay: float  = 3.0 # seconds between API requests to respect rate limits
    timeout_secs : int = 40 
    max_results_per_query: int = 15 
    search_category: str = "cs.AI"
    download_max_retries: int = 3 
    download_retry_delay_secs : float = 5.0
    max_concurrent_downloads : int = 5
    max_concurrent_parsing : int = 1 
    
    namespace: dict  = {
        "atom" : "http://www.w3.org/2005/Atom", # atom is a standard XML namespace for Atom feeds
        "opensearch" : "http://a9.com/-/spec/opensearch/1.1/", # opensearch is a standard XML namespace for OpenSearch
        "arxiv" : "http://arxiv.org/schemas/atom" # arxiv is a custom namespace for arXiv-specific elements

    }

    @field_validator("pdf_cache_dir") # Ensure the PDF cache directory exists 
    @classmethod
    def validate_pdf_cache_dir(cls, v: str) -> str:
        os.makedirs(v, exist_ok=True)
        return v
    

class PDFParserSettings(BaseConfigSettings):
    model_config = SettingsConfigDict(
        env_file=[".env", str(ENV_FILE_PATH)],
        extra="ignore",
        frozen=True,
        env_prefix="PDF_PARSER_",
        case_sensitive=False
    )
    max_pages_to_parse: int = 30  # Limit the number of pages to parse from each PDF
    ocr_enabled: bool = False  # Whether to enable OCR for scanned PDFs
    max_file_size_mb: int = 30
    do_table_struturing: bool = True # Whether to attempt to structure tables in the parsed content

class ChunkingSettings(BaseConfigSettings):
    model_config = SettingsConfigDict(
        env_file=[".env", str(ENV_FILE_PATH)],
        extra="ignore",
        frozen=True,
        env_prefix="CHUNKING_",
        case_sensitive=False
    )
    chunk_size: int = 600
    chunk_overlap: int = 100
    # chunking_strategy: str = "recursive" # or "fixed" or "semantic"
    max_chunk_size: int = 2000
    min_chunk_size: int = 100
    max_chunk_overlap: int = 500
    min_chunk_overlap: int = 50
    section_based_chunking: bool = True # Whether to chunk based on document sections (e.g., headings)

class OpenSearchSettings(BaseConfigSettings):
    model_config = SettingsConfigDict(
        env_file = [".env", str(ENV_FILE_PATH)], 
        env_prefix="OPENSEARCH_",
        extra = "ignore",
        frozen = True,
        case_sensitive = False
    )
    host: str = "https://localhost:9200"
    index_name: str = "arxiv_papers" # base name for the index
    chunk_index_suffix: str = "chunks" # suffix to append to index name for chunked documents
    max_test_size: int = 1000000# size limit for testing index operations

    # vector search settings
    vector_dimension: int = 1024 # dimension of the embedding vectors
    vector_space_type: str = "consinesimil" # consinesimil, l2, innerproduct

    # hybrid search settings
    rrf_pipeline_name: str = "hybrid_search_pipeline" # name of the hybrid search pipeline 
    # Reciprocal Rank Fusion (RRF) is an unsupervised algorithm that combines multiple ranked retrieval lists (e.g., from vector and keyword searches) into a single, highly relevant, and unified ranked list
    hybrid_search_size_multiplier: int = 2 # multiplier for the number of results to retrieve for hybrid search

class LangfuseSettings(BaseConfigSettings):
    model_config = SettingsConfigDict(
        env_file=[".env", str(ENV_FILE_PATH)],
        env_prefix="LANGFUSE_",
        extra="ignore",
        frozen=True,
        case_sensitive=False
    )
    public_key: str = ""
    secret_key: str = ""
    host: str = "http://localhost:3000"
    enabled: bool = False
    flush_at: int = 15 # number of events to batch before flushing to the server
    flush_interval: int = 10 # seconds to wait before flushing events to the server
    max_retries : int = 5 # maximum number of retries for failed requests
    timeout : int = 30 # seconds to wait for a response from the server
    debug : bool = False # whether to enable debug logging

class Settings(BaseConfigSettings):
    app_version: str = "0.1.0"
    debug: bool = True
    environment: Literal["development", "staging", "production"] = "development"
    service_name: str = "rag-api"
    postgress_database_url: str = "postgresql://rag_user:rag_password@localhost:5432/rag_db"
    postgres_echo_sql: bool = False # whether to echo SQL statements to the console
    postgres_pool_size: int = 20 # maximum number of database connections in the pool
    postgres_max_overflow: int = 10 # maximum number of connections to allow in overflow

    ollama_host : str = "http://localhost:11434"
    ollama_model : str = "llama3.2:1b"
    ollama_timeout : int = 300 

    jina_api_key: str = "" # API key for Jina AI services for embeddings

    arxiv: ArxivSettings = Field(default_factory=ArxivSettings)
    pdf_parser: PDFParserSettings = Field(default_factory=PDFParserSettings)
    chunking: ChunkingSettings = Field(default_factory=ChunkingSettings)
    opensearch: OpenSearchSettings = Field(default_factory=OpenSearchSettings)
    langfuse: LangfuseSettings = Field(default_factory=LangfuseSettings)

    @field_validator("postgress_database_url")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        if not v.startswith("postgresql://"):
            raise ValueError("Invalid PostgreSQL database URL")
        return v

def get_settings() -> Settings:
    """Retrieve the application settings."""
    return Settings()

    



## lets use this and print usage 
# if __name__ == "__main__":

#     arxiv_settings = ArxivSettings()
#     print(arxiv_settings.model_dump_json(indent=2))




