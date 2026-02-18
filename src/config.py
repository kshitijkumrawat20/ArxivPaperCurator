from typing import Any, List, Union

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class DefaultSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        frozen=True,
        env_nested_delimiter="__",
        env_parse_enums=True,
    )


class ArxivSettings(DefaultSettings):
    """arXiv API client settings."""

    base_url: str = "https://export.arxiv.org/api/query"
    namespaces: dict = Field(
        default={
            "atom": "http://www.w3.org/2005/Atom",
            "opensearch": "http://a9.com/-/spec/opensearch/1.1/",
            "arxiv": "http://arxiv.org/schemas/atom",
        }
    )
    pdf_cache_dir: str = "./data/arxiv_pdfs"
    rate_limit_delay: float = 3.0  # seconds between requests
    timeout_seconds: int = 30
    max_results: int = 100
    search_category: str = "cs.AI"  # Default category to search
    max_retries: int = 3  # Max retries for API requests
    download_retry_delay_secs: float = 2.0  # Base delay between retries for downloads

class PDFParserSettings(DefaultSettings):
    """PDF parser service settings."""

    max_pages: int = 30
    max_file_size_mb: int = 20
    do_ocr: bool = False
    do_table_structure: bool = True


class Settings(DefaultSettings):
    """Application settings."""

    app_version: str = "0.1.0"
    debug: bool = True
    environment: str = "development"
    service_name: str = "rag-api"

    # PostgreSQL configuration
    postgres_database_url: str = "postgresql://rag_user:rag_password@localhost:5432/rag_db"
    postgres_echo_sql: bool = False
    postgres_pool_size: int = 20
    postgres_max_overflow: int = 0

    # OpenSearch configuration
    opensearch_host: str = "http://localhost:9200"

    # Ollama configuration (used in Week 1 notebook)
    ollama_host: str = "http://localhost:11434"
    ollama_models: str = Field(default="llama3.2:1b")
    ollama_default_model: str = "llama3.2:1b"
    ollama_timeout: int = 300  # 5 minutes for LLM operations

    # arXiv settings
    arxiv: ArxivSettings = Field(default_factory=ArxivSettings)

    # PDF parser settings
    pdf_parser: PDFParserSettings = Field(default_factory=PDFParserSettings)

    @field_validator("ollama_models", mode="after")
    @classmethod
    def validate_ollama_models(cls, v: str) -> str:
        """Validate ollama models string."""
        if not v or not v.strip():
            return "llama3.2:1b"
        return v.strip()
    
    @property
    def ollama_models_list(self) -> List[str]:
        """Get ollama models as a list."""
        if "," in self.ollama_models:
            return [m.strip() for m in self.ollama_models.split(",") if m.strip()]
        return [self.ollama_models]


def get_settings() -> Settings:
    """Get application settings."""
    return Settings()