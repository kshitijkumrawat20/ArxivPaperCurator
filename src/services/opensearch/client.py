"""Unified OpenSearch client supporting both simple BM25 and hybrid search."""

import logging
from typing import Any, Dict, List, Optional

from opensearchpy import OpenSearch
from src.config import Settings
from src.services.metadata_indexing import build_metadata_document, build_metadata_index_action

from .index_config_hybrid import (
    ARXIV_PAPERS_CHUNKS_MAPPING,
    ARXIV_PAPERS_METADATA_MAPPING,
    HYBRID_RRF_PIPELINE,
)
from .query_builder import QueryBuilder

logger = logging.getLogger(__name__)


class OpenSearchClient:
    """OpenSearch client supporting BM25 and hybrid search with native RRF."""

    def __init__(self, host: str, settings: Settings):
        self.host = host
        self.settings = settings
        self.index_name = f"{settings.opensearch.index_name}-{settings.opensearch.chunk_index_suffix}"
        self.metadata_index_name = f"{settings.opensearch.index_name}-{settings.opensearch.metadata_index_suffix}"

        self.client = OpenSearch(
            hosts=[host],
            use_ssl=False,
            verify_certs=False,
            ssl_show_warn=False,
        )

        logger.info(f"OpenSearch client initialized with host: {host}")

    def health_check(self) -> bool:
        """Check if OpenSearch cluster is healthy."""
        try:
            health = self.client.cluster.health()
            return health["status"] in ["green", "yellow"]
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False

    def get_index_stats(self) -> Dict[str, Any]:
        """Get statistics for the hybrid index."""
        try:
            if not self.client.indices.exists(index=self.index_name):
                return {"index_name": self.index_name, "exists": False, "document_count": 0}

            stats_response = self.client.indices.stats(index=self.index_name)
            index_stats = stats_response["indices"][self.index_name]["total"]

            return {
                "index_name": self.index_name,
                "exists": True,
                "document_count": index_stats["docs"]["count"],
                "deleted_count": index_stats["docs"]["deleted"],
                "size_in_bytes": index_stats["store"]["size_in_bytes"],
            }

        except Exception as e:
            logger.error(f"Error getting index stats: {e}")
            return {"index_name": self.index_name, "exists": False, "document_count": 0, "error": str(e)}

    def setup_indices(self, force: bool = False) -> Dict[str, bool]:
        """Setup both search indexes and the hybrid RRF pipeline."""
        results = {}
        results["hybrid_index"] = self._create_hybrid_index(force)
        results["rrf_pipeline"] = self._create_rrf_pipeline(force)
        results["metadata_index"] = self._create_metadata_index(force)
        return results

    def _create_metadata_index(self, force: bool = False) -> bool:
        """Create the independent, vector-free paper metadata index."""
        try:
            if force and self.client.indices.exists(index=self.metadata_index_name):
                self.client.indices.delete(index=self.metadata_index_name)
            if not self.client.indices.exists(index=self.metadata_index_name):
                self.client.indices.create(index=self.metadata_index_name, body=ARXIV_PAPERS_METADATA_MAPPING)
                return True
            return False
        except Exception as exc:
            # Metadata discovery is additive; do not take down the established
            # chunk/hybrid index startup if its separate index cannot be prepared.
            logger.error("Could not initialize metadata discovery index (%s)", type(exc).__name__)
            return False

    def index_paper_metadata(self, paper: Any) -> bool:
        """Idempotently index one PostgreSQL paper using its exact arXiv ID."""
        try:
            doc = build_metadata_document(paper)
            response = self.client.index(index=self.metadata_index_name, id=doc["arxiv_id"], body=doc, refresh=True)
            return response.get("result") in {"created", "updated", "noop"}
        except Exception as exc:
            logger.warning("Metadata indexing failed (%s)", type(exc).__name__)
            return False

    def bulk_index_paper_metadata(self, papers: List[Any]) -> Dict[str, Any]:
        """Bulk upsert metadata documents, returning per-record failures for retry."""
        from opensearchpy import helpers

        actions = [build_metadata_index_action(paper, self.metadata_index_name) for paper in papers]
        success, failed = helpers.bulk(self.client, actions, refresh=True, raise_on_error=False)
        return {"success": success, "failed": len(failed), "errors": failed}

    def search_paper_metadata(self, body: Dict[str, Any]) -> Dict[str, Any]:
        """Search the paper-level metadata index using a prebuilt BM25 query."""
        return self.client.search(index=self.metadata_index_name, body=body)

    def _create_hybrid_index(self, force: bool = False) -> bool:
        """Create hybrid index for all search types (BM25, vector, hybrid).

        :param force: If True, recreate index even if it exists
        :returns: True if created, False if already exists
        """
        try:
            if force and self.client.indices.exists(index=self.index_name):
                self.client.indices.delete(index=self.index_name)
                logger.info(f"Deleted existing hybrid index: {self.index_name}")

            if not self.client.indices.exists(index=self.index_name):
                self.client.indices.create(index=self.index_name, body=ARXIV_PAPERS_CHUNKS_MAPPING)
                logger.info(f"Created hybrid index: {self.index_name}")
                return True

            logger.info(f"Hybrid index already exists: {self.index_name}")
            return False

        except Exception as e:
            logger.error(f"Error creating hybrid index: {e}")
            raise

    def _create_rrf_pipeline(self, force: bool = False) -> bool:
        """Create RRF search pipeline for native hybrid search.

        :param force: If True, recreate pipeline even if it exists
        :returns: True if created, False if already exists
        """
        try:
            pipeline_id = HYBRID_RRF_PIPELINE["id"]

            if force:
                try:
                    self.client.ingest.get_pipeline(id=pipeline_id)
                    self.client.ingest.delete_pipeline(id=pipeline_id)
                    logger.info(f"Deleted existing RRF pipeline: {pipeline_id}")
                except Exception:
                    pass

            try:
                self.client.ingest.get_pipeline(id=pipeline_id)
                logger.info(f"RRF pipeline already exists: {pipeline_id}")
                return False
            except Exception:
                pass
            pipeline_body = {
                "description": HYBRID_RRF_PIPELINE["description"],
                "phase_results_processors": HYBRID_RRF_PIPELINE["phase_results_processors"],
            }

            self.client.transport.perform_request("PUT", f"/_search/pipeline/{pipeline_id}", body=pipeline_body)

            logger.info(f"Created RRF search pipeline: {pipeline_id}")
            return True

        except Exception as e:
            logger.error(f"Error creating RRF pipeline: {e}")
            raise

    def search_papers(
        self, query: str, size: int = 10, from_: int = 0, categories: Optional[List[str]] = None,
        latest: bool = True, arxiv_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """BM25 search for papers."""
        return self._search_bm25_only(
            query=query, size=size, from_=from_, categories=categories, latest=latest, arxiv_id=arxiv_id
        )

    def search_chunks_vector(
        self, query_embedding: List[float], size: int = 10, categories: Optional[List[str]] = None,
        arxiv_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Pure vector search on chunks.

        :param query_embedding: Query embedding vector
        :param size: Number of results
        :param categories: Optional category filter
        :returns: Search results
        """
        try:
            # Build filter
            filter_clause = []
            if categories:
                filter_clause.append({"terms": {"categories": categories}})
            if arxiv_id:
                filter_clause.append({"term": {"arxiv_id": arxiv_id}})

            search_body = {
                "size": size,
                "query": {"knn": {"embedding": {"vector": query_embedding, "k": size}}},
                "_source": {"excludes": ["embedding"]},
            }

            if filter_clause:
                search_body["query"] = {"bool": {"must": [search_body["query"]], "filter": filter_clause}}

            response = self.client.search(index=self.index_name, body=search_body)

            results = {"total": response["hits"]["total"]["value"], "hits": []}

            for hit in response["hits"]["hits"]:
                chunk = hit["_source"]
                chunk["score"] = hit["_score"]
                chunk["chunk_id"] = hit["_id"]
                results["hits"].append(chunk)

            return results

        except Exception as e:
            logger.error(f"Vector search error: {e}")
            return {"total": 0, "hits": []}

    def search_unified(
        self,
        query: str,
        query_embedding: Optional[List[float]] = None,
        size: int = 10,
        from_: int = 0,
        categories: Optional[List[str]] = None,
        latest: bool = False,
        use_hybrid: bool = True,
        min_score: float = 0.0,
        arxiv_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Unified search method supporting BM25, vector, and hybrid modes.

        :param query: Text query for search
        :param query_embedding: Optional embedding for vector/hybrid search
        :param size: Number of results to return
        :param from_: Offset for pagination
        :param categories: Optional category filter
        :param latest: Sort by date instead of relevance
        :param use_hybrid: If True and embedding provided, use hybrid search
        :param min_score: Minimum score threshold
        :returns: Search results
        """
        try:
            # If no embedding provided or hybrid disabled, use BM25 only
            if not query_embedding or not use_hybrid:
                return self._search_bm25_only(
                    query=query, size=size, from_=from_, categories=categories, latest=latest, arxiv_id=arxiv_id
                )

            # Use native OpenSearch hybrid search with RRF pipeline
            return self._search_hybrid_native(
                query=query,
                query_embedding=query_embedding,
                size=size,
                from_=from_,
                categories=categories,
                min_score=min_score,
                arxiv_id=arxiv_id,
            )

        except Exception as e:
            logger.error(f"Unified search error: {e}")
            if arxiv_id is not None:
                raise
            return {"total": 0, "hits": []}

    def _search_bm25_only(
        self, query: str, size: int, from_: int, categories: Optional[List[str]], latest: bool,
        arxiv_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Pure BM25 search implementation."""
        builder = QueryBuilder(
            query=query,
            size=size,
            from_=from_,
            categories=categories,
            latest_papers=latest,
            search_chunks=True,  # Enable chunk search mode
            arxiv_id=arxiv_id,
        )
        search_body = builder.build()

        response = self.client.search(index=self.index_name, body=search_body)

        results = {"total": response["hits"]["total"]["value"], "hits": []}

        for hit in response["hits"]["hits"]:
            chunk = hit["_source"]
            chunk["score"] = hit["_score"]
            chunk["chunk_id"] = hit["_id"]

            if "highlight" in hit:
                chunk["highlights"] = hit["highlight"]

            results["hits"].append(chunk)

        logger.info(f"BM25 search for '{query[:50]}...' returned {results['total']} results")
        return results

    def _search_hybrid_native(
        self,
        query: str,
        query_embedding: List[float],
        size: int,
        from_: int,
        categories: Optional[List[str]],
        min_score: float,
        arxiv_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Native OpenSearch hybrid search with RRF pipeline."""
        candidate_count = (from_ + size) * 2
        builder = QueryBuilder(
            query=query, size=candidate_count, from_=0, categories=categories, latest_papers=False,
            search_chunks=True, arxiv_id=arxiv_id,
        )
        bm25_search_body = builder.build()

        bm25_query = bm25_search_body["query"]
        vector_query = {"knn": {"embedding": {"vector": query_embedding, "k": candidate_count}}}
        vector_filters = []
        if categories:
            vector_filters.append({"terms": {"categories": categories}})
        if arxiv_id:
            vector_filters.append({"term": {"arxiv_id": arxiv_id}})
        if vector_filters:
            vector_query = {
                "bool": {
                    "must": [vector_query],
                    "filter": vector_filters,
                }
            }

        hybrid_query = {"hybrid": {"queries": [bm25_query, vector_query]}}

        search_body = {
            "size": size,
            "from": from_,
            "min_score": min_score,
            "query": hybrid_query,
            "_source": bm25_search_body["_source"],
            "highlight": bm25_search_body["highlight"],
        }

        # Execute search with RRF pipeline
        response = self.client.search(
            index=self.index_name, body=search_body, params={"search_pipeline": HYBRID_RRF_PIPELINE["id"]}
        )

        results = {"total": response["hits"]["total"]["value"], "hits": []}

        for hit in response["hits"]["hits"]:
            chunk = hit["_source"]
            chunk["score"] = hit["_score"]
            chunk["chunk_id"] = hit["_id"]

            if "highlight" in hit:
                chunk["highlights"] = hit["highlight"]

            results["hits"].append(chunk)

        logger.info(f"Native hybrid search for '{query[:50]}...' returned {results['total']} results")
        return results

    def search_chunks_hybrid(
        self,
        query: str,
        query_embedding: List[float],
        size: int = 10,
        categories: Optional[List[str]] = None,
        min_score: float = 0.0,
        from_: int = 0,
        arxiv_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Hybrid search combining BM25 and vector similarity using native RRF."""
        return self._search_hybrid_native(
            query=query,
            query_embedding=query_embedding,
            size=size,
            from_=from_,
            categories=categories,
            min_score=min_score,
            arxiv_id=arxiv_id,
        )

    def index_chunk(self, chunk_data: Dict[str, Any], embedding: List[float]) -> bool:
        """Index a single chunk with its embedding.

        :param chunk_data: Chunk data dictionary
        :param embedding: Embedding vector
        :returns: True if successful
        """
        try:
            chunk_data["embedding"] = embedding

            response = self.client.index(index=self.index_name, body=chunk_data, refresh=True)

            return response["result"] in ["created", "updated"]

        except Exception as e:
            logger.error(f"Error indexing chunk: {e}")
            return False

    def bulk_index_chunks(self, chunks: List[Dict[str, Any]]) -> Dict[str, int]:
        """Bulk index multiple chunks with embeddings.

        :param chunks: List of dicts with 'chunk_data' and 'embedding'
        :returns: Statistics
        """
        from opensearchpy import helpers

        try:
            actions = []
            for chunk in chunks:
                chunk_data = chunk["chunk_data"].copy()
                chunk_data["embedding"] = chunk["embedding"]

                action = {"_index": self.index_name, "_source": chunk_data}
                actions.append(action)

            success, failed = helpers.bulk(self.client, actions, refresh=True)

            logger.info(f"Bulk indexed {success} chunks, {len(failed)} failed")
            return {"success": success, "failed": len(failed)}

        except Exception as e:
            logger.error(f"Bulk chunk indexing error: {e}")
            raise

    def delete_paper_chunks(self, arxiv_id: str) -> bool:
        """Delete all chunks for a specific paper.

        :param arxiv_id: ArXiv ID of the paper
        :returns: True if deletion was successful
        """
        try:
            response = self.client.delete_by_query(
                index=self.index_name, body={"query": {"term": {"arxiv_id": arxiv_id}}}, refresh=True
            )

            deleted = response.get("deleted", 0)
            logger.info(f"Deleted {deleted} chunks for paper {arxiv_id}")
            return deleted > 0

        except Exception as e:
            logger.error(f"Error deleting chunks: {e}")
            return False

    def get_chunks_by_paper(
        self, arxiv_id: str, limit: int = 1000, raise_errors: bool = False
    ) -> List[Dict[str, Any]]:
        """Get all chunks for a specific paper.

        :param arxiv_id: ArXiv ID of the paper
        :returns: List of chunks sorted by chunk_index
        """
        try:
            search_body = {
                "query": {"term": {"arxiv_id": arxiv_id}},
                "size": limit,
                "sort": [{"chunk_index": "asc"}],
                "_source": {"excludes": ["embedding"]},
            }

            response = self.client.search(index=self.index_name, body=search_body)

            chunks = []
            for hit in response["hits"]["hits"]:
                chunk = hit["_source"]
                chunk["chunk_id"] = hit["_id"]
                chunks.append(chunk)

            return chunks

        except Exception as e:
            logger.error(f"Error getting chunks: {e}")
            if raise_errors:
                raise
            return []
