from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.schema.api.ask import PaperAskRequest
from src.services.paper_scoped_rag import (
    NO_EVIDENCE_ANSWER,
    PaperGenerationUnavailableError,
    PaperNotFoundError,
    PaperNotIndexedError,
    PaperScopedRAGService,
    PaperSearchUnavailableError,
    PaperSearchUnavailableError,
)


ARXIV_ID = "1706.03762v7"


def make_service(*, paper=True, chunks=None, search=None, embedding=None, cache=None):
    repository = MagicMock()
    repository.get_by_arxiv_id.return_value = SimpleNamespace(pdf_url=f"https://arxiv.org/pdf/{ARXIV_ID}") if paper else None
    opensearch = MagicMock()
    opensearch.get_chunks_by_paper.return_value = chunks if chunks is not None else [{"chunk_id": "probe"}]
    opensearch.search_unified.return_value = search if search is not None else {
        "total": 1,
        "hits": [{
            "arxiv_id": ARXIV_ID, "chunk_id": "chunk-7", "chunk_index": 7,
            "section_title": "Method", "chunk_text": "The paper describes attention.",
        }],
    }
    embeddings = MagicMock()
    embeddings.embed_query = AsyncMock(return_value=[0.1, 0.2])
    if isinstance(embedding, Exception):
        embeddings.embed_query.side_effect = embedding
    ollama = MagicMock()
    ollama.generate_rag_answer = AsyncMock(return_value={"answer": "Attention is described in the excerpt."})
    tracer = MagicMock()
    for method in ("trace_request", "trace_embedding", "trace_search", "trace_prompt_construction", "trace_generation"):
        getattr(tracer, method).return_value = nullcontext(MagicMock())
    service = PaperScopedRAGService(repository, opensearch, embeddings, ollama, tracer, cache)
    return service, repository, opensearch, embeddings, ollama, tracer


@pytest.mark.asyncio
async def test_hybrid_rag_passes_exact_paper_filter_and_only_generates_from_selected_hits():
    search = {"total": 2, "hits": [
        {"arxiv_id": ARXIV_ID, "chunk_id": "chunk-7", "chunk_index": 7,
         "section_title": "Method", "chunk_text": "Selected paper evidence."},
        {"arxiv_id": "1801.00001v1", "chunk_id": "foreign", "chunk_text": "Must be discarded."},
    ]}
    service, _, opensearch, embeddings, ollama, _ = make_service(search=search)
    request = PaperAskRequest(query="What is the method?", top_k=2, use_hybrid=True, model="model-x")

    result = await service.ask(ARXIV_ID, request)

    search_args = opensearch.search_unified.call_args.kwargs
    assert search_args["arxiv_id"] == ARXIV_ID
    assert search_args["size"] == 2
    assert search_args["use_hybrid"] is True
    embeddings.embed_query.assert_awaited_once_with(request.query)
    generation = ollama.generate_rag_answer.call_args.kwargs
    assert generation["model"] == "model-x"
    assert generation["paper_scope"] == ARXIV_ID
    assert [chunk["arxiv_id"] for chunk in generation["chunks"]] == [ARXIV_ID]
    assert result.retrieval_mode == "hybrid"
    assert result.evidence[0].chunk_id == "chunk-7"
    assert result.evidence[0].section_title == "Method"
    assert result.evidence[0].excerpt == "Selected paper evidence."


@pytest.mark.asyncio
async def test_bm25_mode_respects_top_k_and_does_not_embed():
    service, _, opensearch, embeddings, _, _ = make_service()
    result = await service.ask(ARXIV_ID, PaperAskRequest(query="question", top_k=4, use_hybrid=False, model="m"))

    embeddings.embed_query.assert_not_awaited()
    assert opensearch.search_unified.call_args.kwargs["arxiv_id"] == ARXIV_ID
    assert opensearch.search_unified.call_args.kwargs["size"] == 4
    assert opensearch.search_unified.call_args.kwargs["use_hybrid"] is False
    assert result.retrieval_mode == "bm25"


@pytest.mark.asyncio
async def test_embedding_failure_falls_back_only_to_scoped_bm25():
    service, _, opensearch, _, _, _ = make_service(embedding=RuntimeError("embedding offline"))

    result = await service.ask(ARXIV_ID, PaperAskRequest(query="question", use_hybrid=True))

    assert opensearch.search_unified.call_args.kwargs["arxiv_id"] == ARXIV_ID
    assert opensearch.search_unified.call_args.kwargs["use_hybrid"] is False
    assert result.retrieval_mode == "bm25"


@pytest.mark.asyncio
async def test_no_global_fallback_and_no_generation_when_only_foreign_hits_return():
    service, _, opensearch, _, ollama, _ = make_service(
        search={"total": 1, "hits": [{"arxiv_id": "2401.00001v2", "chunk_text": "foreign"}]}
    )

    result = await service.ask(ARXIV_ID, PaperAskRequest(query="not present", use_hybrid=False))

    assert opensearch.search_unified.call_args.kwargs["arxiv_id"] == ARXIV_ID
    ollama.generate_rag_answer.assert_not_awaited()
    assert result.answer == NO_EVIDENCE_ANSWER
    assert result.evidence == [] and result.chunks_used == 0


@pytest.mark.asyncio
async def test_missing_and_unindexed_papers_are_distinct():
    missing, *_ = make_service(paper=False)
    with pytest.raises(PaperNotFoundError):
        await missing.ask(ARXIV_ID, PaperAskRequest(query="question"))

    unindexed, _, opensearch, _, _, _ = make_service(chunks=[])
    with pytest.raises(PaperNotIndexedError):
        await unindexed.ask(ARXIV_ID, PaperAskRequest(query="question"))
    opensearch.search_unified.assert_not_called()


@pytest.mark.asyncio
async def test_search_and_generation_failures_are_reported_not_treated_as_no_evidence():
    service, _, opensearch, _, _, _ = make_service()
    opensearch.search_unified.side_effect = RuntimeError("search offline")
    with pytest.raises(PaperSearchUnavailableError):
        await service.ask(ARXIV_ID, PaperAskRequest(query="question", use_hybrid=False))

    service, _, _, _, ollama, _ = make_service()
    ollama.generate_rag_answer.side_effect = RuntimeError("generation offline")
    with pytest.raises(PaperGenerationUnavailableError):
        await service.ask(ARXIV_ID, PaperAskRequest(query="question", use_hybrid=False))
