"""Evidence-grounded RAG restricted to one exact, versioned arXiv ID."""

import logging
import time
from typing import Any

from src.schema.api.ask import PaperAskRequest, PaperAskResponse, PaperChunkReference

logger = logging.getLogger(__name__)

NO_EVIDENCE_ANSWER = (
    "I couldn't find relevant evidence in the indexed full text of the selected paper "
    "to answer this question."
)


class PaperNotFoundError(Exception):
    pass


class PaperNotIndexedError(Exception):
    pass


class PaperSearchUnavailableError(Exception):
    pass


class PaperGenerationUnavailableError(Exception):
    pass


class PaperScopedRAGService:
    def __init__(
        self,
        paper_repository: Any,
        opensearch_client: Any,
        embeddings_service: Any,
        ollama_client: Any,
        rag_tracer: Any,
        cache_client: Any = None,
    ):
        self.paper_repository = paper_repository
        self.opensearch_client = opensearch_client
        self.embeddings_service = embeddings_service
        self.ollama_client = ollama_client
        self.rag_tracer = rag_tracer
        self.cache_client = cache_client

    async def ask(self, arxiv_id: str, request: PaperAskRequest) -> PaperAskResponse:
        paper = self.paper_repository.get_by_arxiv_id(arxiv_id)
        if paper is None:
            raise PaperNotFoundError(arxiv_id)

        # This bounded probe distinguishes metadata-only papers from a query with
        # no relevant match. It raises on OpenSearch failure instead of masking it.
        try:
            available_chunks = self.opensearch_client.get_chunks_by_paper(
                arxiv_id, limit=1, raise_errors=True
            )
        except Exception as exc:
            raise PaperSearchUnavailableError("Could not check indexed paper chunks") from exc
        if not available_chunks:
            raise PaperNotIndexedError(arxiv_id)

        rag_tracer = self.rag_tracer
        started = time.time()
        with rag_tracer.trace_request(
            "api_user", request.query, metadata={"scope": "paper", "arxiv_id": arxiv_id}
        ) as trace:
            if self.cache_client:
                try:
                    cached = await self.cache_client.find_cached_paper_response(request, arxiv_id)
                    if cached and cached.arxiv_id == arxiv_id:
                        rag_tracer.end_request(trace, cached.answer, time.time() - started)
                        return cached
                except Exception as exc:
                    logger.warning("Paper-scoped cache lookup failed (%s)", type(exc).__name__)

            query_embedding = None
            retrieval_mode = "bm25"
            if request.use_hybrid:
                with rag_tracer.trace_embedding(trace, request.query) as embedding_span:
                    try:
                        query_embedding = await self.embeddings_service.embed_query(request.query)
                        retrieval_mode = "hybrid"
                    except Exception as exc:
                        # Embedding failure may degrade to scoped BM25, never global retrieval.
                        logger.warning("Paper-scoped embedding failed; using scoped BM25 (%s)", type(exc).__name__)
                        if embedding_span:
                            rag_tracer.tracer.update_span(
                                embedding_span, output={"success": False, "error": type(exc).__name__}
                            )

            try:
                with rag_tracer.trace_search(trace, request.query, request.top_k, arxiv_id=arxiv_id) as search_span:
                    results = self.opensearch_client.search_unified(
                        query=request.query,
                        query_embedding=query_embedding,
                        size=request.top_k,
                        from_=0,
                        use_hybrid=retrieval_mode == "hybrid",
                        min_score=0.0,
                        arxiv_id=arxiv_id,
                    )
                    # Defense in depth: never allow a malformed/mock/broken backend
                    # response to widen the selected paper boundary.
                    selected_hits = [
                        hit for hit in results.get("hits", []) if hit.get("arxiv_id") == arxiv_id
                    ]
                    chunks = [
                        {
                            "arxiv_id": arxiv_id,
                            "chunk_text": hit.get("chunk_text", ""),
                            "chunk_id": hit.get("chunk_id"),
                            "chunk_index": hit.get("chunk_index"),
                            "section_title": hit.get("section_title"),
                        }
                        for hit in selected_hits
                        if hit.get("chunk_text")
                    ]
                    rag_tracer.end_search(search_span, chunks, [arxiv_id] if chunks else [], len(chunks))
            except Exception as exc:
                raise PaperSearchUnavailableError("Paper-scoped search failed") from exc

            if not chunks:
                response = PaperAskResponse(
                    query=request.query,
                    answer=NO_EVIDENCE_ANSWER,
                    arxiv_id=arxiv_id,
                    source_url=paper.pdf_url,
                    evidence=[],
                    chunks_used=0,
                    retrieval_mode=retrieval_mode,
                )
                rag_tracer.end_request(trace, response.answer, time.time() - started)
                return response

            try:
                with rag_tracer.trace_prompt_construction(trace, chunks) as prompt_span:
                    prompt_summary = (
                        f"Paper-scoped prompt for arXiv:{arxiv_id} using {len(chunks)} retrieved excerpt(s)"
                    )
                    rag_tracer.end_prompt(prompt_span, prompt_summary)
                with rag_tracer.trace_generation(trace, request.model, prompt_summary) as generation_span:
                    generated = await self.ollama_client.generate_rag_answer(
                        query=request.query,
                        chunks=chunks,
                        model=request.model,
                        paper_scope=arxiv_id,
                    )
                    answer = generated.get("answer") or "Unable to generate an answer from the selected paper."
                    rag_tracer.end_generation(generation_span, answer, request.model)
            except Exception as exc:
                raise PaperGenerationUnavailableError("Paper-scoped answer generation failed") from exc

            response = PaperAskResponse(
                query=request.query,
                answer=answer,
                arxiv_id=arxiv_id,
                source_url=paper.pdf_url,
                evidence=[
                    PaperChunkReference(
                        chunk_id=chunk.get("chunk_id"),
                        chunk_index=chunk.get("chunk_index"),
                        section_title=chunk.get("section_title"),
                        excerpt=chunk["chunk_text"],
                    )
                    for chunk in chunks
                ],
                chunks_used=len(chunks),
                retrieval_mode=retrieval_mode,
            )
            rag_tracer.end_request(trace, answer, time.time() - started)

            if self.cache_client:
                try:
                    await self.cache_client.store_paper_response(request, arxiv_id, response)
                except Exception as exc:
                    logger.warning("Paper-scoped cache write failed (%s)", type(exc).__name__)
            return response
