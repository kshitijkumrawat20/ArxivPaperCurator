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
    pdf_cache_dir: str = "./data/arxiv_pdfs", 
    rate_limit_delay: str = 3.0 # seconds between API requests to respect rate limits
    timeout_secs : int = 40 ,
    max_results_per_query: int = 15 ,
    search_category: str = "cs.AI",
    download_max_retries: int = 3,  
    download_retry_delay_secs : float = 5.0,
    max_concurrent_downlaods : int = 5,
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
    

