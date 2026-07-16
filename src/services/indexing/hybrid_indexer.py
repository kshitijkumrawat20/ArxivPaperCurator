# Add orchestration: chunk paper, generate embeddings, bulk index chunks

import logging
from typing import Dict, List, Optional
from src.services.embeddings.jina_client import JinaEmbeddingsClient
from src.services.opensearch.client import OpenSearchClient
from .text_chunker import TextChunker 

logger  = logging.getLogger(__name__)

class HybridIndexingService: 
    """
    Service for indexing papers with chunking and embeddings for hybrid search.

    Orchestrates the process of:
    1. Chunking papers into overlapping segments
    2. Generating embeddings for each chunk
    3. Indexing chunks with embeddings into OpenSearch
    """

    def __init__(self,
                 chunker: TextChunker, 
                 embeddings_client: JinaEmbeddingsClient,
                 opensearch_client: OpenSearchClient):
        """
        Initialize hybrid indexing service.

        :param chunker: Text chunking service
        :param embeddings_client: Embeddings generation client
        :param opensearch_client: OpenSearch client
        """
        self.chunker = chunker
        self.embeddings_client = embeddings_client
        self.opensearch_client = opensearch_client

        logger.info("Hybrid Indexing service initialized")
    
    async def index_paper(self, paper_data: Dict) -> Dict[str,int]:
        """Index a single paper with chunking and embeddings.

        :param paper_data: Paper data from database
        :returns: Dictionary with indexing statistics
        """
        arxiv_id  = paper_data.get("arxiv_id")
        paper_id = str(paper_data.get("id",""))

        if not arxiv_id: 
            logger.error("Paper missing arxiv_id")
            return {
                "chunks_created": 0,
                "chunks_indexed": 0,
                "embeddings_generated": 0,
                "error": 1
            }
        
        try: 
            # Step 1: chunk the paper using hybrid section based chunking 
            chunks = self.chunker.chunk_paper(
                title = paper_data.get("title", ""),
                abstract = paper_data.get("abstract", ""),
                full_text = paper_data.get("raw_text", paper_data.get("full_text", "")),
                arxiv_id = arxiv_id,
                paper_id = paper_id,
                sections = paper_data.get("sections"),
            )
            if not chunks : 
                logger.warning(f"No chunks created for paper {arxiv_id}")
                return {
                    "chunks_created": 0,
                    "chunks_indexed": 0,
                    "embeddings_generated": 0,
                    "error": 0
                }
            logger.info(f"Created {len(chunks)} chunks for paper {arxiv_id}")

            # Step 2: generate embeddings for each chunk    
            chunk_texts = [chunk.text for chunk in chunks]
            embeddings = await self.embeddings_client.embed_passages(
                texts = chunk_texts,
                batch_size = 50, # process in batches
            )

            if len(embeddings) != len(chunks):
                logger.error(f"Embedding count missmatch: {len(embeddings)} embeddings for {len(chunks)} chunks")
                return {
                    "chunks_created": len(chunks),
                    "chunks_indexed": 0,
                    "embeddings_generated": len(embeddings),
                    "error": 1
                }
            
            # Step 3: index chunks with embeddings into OpenSearch
            chunks_with_embeddings = []
            for chunk, embedding in zip(chunks, embeddings):
                # prepare chunk data for opensearch
                chunk_data = {
                    "arxiv_id": arxiv_id,
                    "paper_id": paper_id,
                    "chunk_index": chunk.metadata.chunk_index,
                    "chunk_text": chunk.text,
                    "chunk_word_count": chunk.metadata.word_count,
                    "start_char": chunk.metadata.start_char_index,
                    "end_char": chunk.metadata.end_char_index,
                    "embedding_model": "jina-embeddings-v3",
                    "title": paper_data.get("title", ""),
                    "authors": ", ".join(paper_data.get("authors", [])) if isinstance(paper_data.get("authors"), list ) else paper_data.get("abstract", ""),
                    "abstract": paper_data.get("abstract", ""),
                    "categories": paper_data.get("categories", []),
                    "published_date": paper_data.get("published_date"),

                    
                }
                chunks_with_embeddings.append(
                    {
                        "chunk_data": chunk_data,
                        "embedding": embedding
                    }
                )

                # Step 4: bulk index chunks into OpenSearch
                results = self.opensearch_client.bulk_index_chunks(
                    chunks_with_embeddings
                )
                logger.info(f"Indexed {arxiv_id}: {results['success']} chunks successfull, {results['failed']} chunks failed")

                return {
                    "chunks_created": len(chunks),
                    "chunks_indexed": results['success'],
                    "embeddings_generated": len(embeddings),
                    "error": results['failed'],
                }
        except Exception as e:
            logger.error(f"Error indexing paper {arxiv_id}: {e}")
            return {"chunks_created": 0, "chunks_indexed": 0, "embeddings_generated": 0, "error": 1}
    
    async def index_papers_batch(self, papers: List[Dict],replace_existing: bool = False) -> Dict[str, int]:
        """Index multiple papers in batch.

        :param papers: List of paper data
        :param replace_existing: If True, delete existing chunks before indexing
        :returns: Aggregated statistics
        """
        total_stats = {
            "papers_processed": 0,
            "total_chunks_created": 0,
            "total_chunks_indexed": 0,
            "total_embeddings_generated": 0,
            "total_errors": 0
        }
        for paper in papers: 
            arxiv_id = paper.get("arxiv_id")
            # Optionally delete existing chunks 
            if replace_existing and arxiv_id : 
                self.opensearch_client.delete_paper_chunks(
                    arxiv_id = arxiv_id
                )
            # Index the paper 
            stats = await self.index_paper(paper)

            # update totals 
            total_stats["papers_processed"] += 1
            total_stats["total_chunks_created"] += stats["chunks_created"]
            total_stats["total_chunks_indexed"] += stats["chunks_indexed"]
            total_stats["total_embeddings_generated"] += stats["embeddings_generated"]
            total_stats["total_errors"] += stats["error"]

        logger.info(
            f"Batch indexing complete: {total_stats['papers_processed']} papers, "
            f"{total_stats['total_chunks_indexed']} chunks indexed"
        )
        return total_stats
    
    async def reindex_paper(self,arxiv_id: str, paper_data: Dict) -> Dict[str,int]:
        """Reindex a single paper by deleting existing chunks and reindexing.

        :param arxiv_id: Arxiv ID of the paper
        :param paper_data: Updated paper data 
        :returns: Dictionary with indexing statistics
        """
        deleted = self.opensearch_client.delete_paper_chunks(arxiv_id)
        if deleted:
            logger.info(f"Deleted existing chunks for paper {arxiv_id}, reindexing...")
        
        # Index with new data 
        return await self.index_paper(paper_data)
    