import logging 
from datetime import datetime, timezone 
from typing import Any, Dict, List, Optional 
from opensearchpy import OpenSearch 
from opensearchpy.exceptions import NotFoundError, RequestError 
from src.config import Settings, get_settings 
from .index_config import ARXIV_PAPER_INDEX, ARXIV_PAPER_MAPPING
from .query_builder import PaperQueryBuilder

logger = logging.getLogger(__name__)

class OpenSearchClient: 
    """
    Client for opensearch operations including index management and search. 

    This client provides methods for creating indices, indexing papers, searching with BM25 scoring, and managing OpenSearch cluster operations.
    """

    def __init__(self, host: str = "http://localhost:9200",
                 settings: Optional[Settings] = None):
        """
        Initialize Opensearch client.
        param host: OpenSearch cluster endpoint URL
        :param settings: Application settings instance (uses default if None)
        :type host: str
        :type settings: Optional[Settings]

        """
        self.host = host 
        self.settings = settings or get_settings()
        self.index_name = self.settings.opensearch.index_name 
        self.client = OpenSearch(
            hosts=[host],
            http_compress = True, # enables gzip compression for request bodies
            use_ssl = False, 
            verify_certs = False,
            ssl_assert_hostname = False, 
            ssl_show_warn =False,
        )

        # use configured index name , fall back to constant if not set 

        self.index_name = self.settings.opensearch.index_name or ARXIV_PAPER_INDEX
        logger.info(f"OpenSearch client initialized with host: {host}")

    def create_index(self, force: bool = False) -> bool:
        """Create the arxiv-papers index with proper mappings.

        :param force: If True, delete existing index before creating
        :type force: bool
        :returns: True if index was created, False if it already exists
        :rtype: bool
        """
        try: 
            # check if index exists 
            if self.client.indices.exists(index=self.index_name):
                if force: 
                    logger.info(f"Deleting existing index: {self.index_name}")
                    self.client.indices.delete(index=self.index_name)
                else: 
                    logger.info(f"Index {self.index_name} already exists. Skipping creation.")
                    return False
            # create index with mappings

            response = self.client.indices.create(index=self.index_name, body=ARXIV_PAPER_MAPPING)

            if response.get("acknowledged"):
                logger.info(f"Index {self.index_name} created successfully.")
                return True
            else: 
                logger.error(f"Failed to create index {self.index_name}. Response: {response}")
                return False
            
        except RequestError as e:
            logger.error(f"RequestError while creating index {self.index_name}: {e.info}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error while creating index {self.index_name}: {str(e)}")
            return False
    
    