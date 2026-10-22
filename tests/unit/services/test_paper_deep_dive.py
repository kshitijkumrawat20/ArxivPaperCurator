import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.schema.api.deep_dive import PaperDeepDiveRequest
from src.services.paper_deep_dive import (
    PROMPT_VERSION,
    PaperDeepDiveGenerationUnavailableError,
    PaperDeepDiveInsufficientEvidenceError,
    PaperDeepDiveNotFoundError,
    PaperDeepDiveNotPreparedError,
    PaperDeepDiveService,
)


ARXIV_ID = "1706.03762v7"
EXCERPT = "The method uses attention over learned representations."


def generated_brief(*, valid_ref=True, unknowns=True):
    return {
        "executive_summary": "The paper studies attention.",
        "problem_statement": "How to represent sequence context.",
        "key_contributions": ["It proposes an attention mechanism."],
        "methodology": "Attention is applied over learned representations.",
        "experimental_results": "Unavailable from the retrieved paper evidence." if unknowns else "Reported result.",
        "author_stated_limitations": [],
        "system_inferred_caveats": [],
        "implementation_details": "Unavailable from the retrieved paper evidence.",
        "practical_engineering_takeaways": [
            {"takeaway": "Consider attention for sequence context.", "basis": "engineering_inference"}
        ],
        "evidence_references": [{
            "chunk_id": "chunk-1" if valid_ref else "not-retrieved",
            "section_name": "Method",
            "excerpt": EXCERPT if valid_ref else "Invented excerpt",
        }],
        "information_gaps": [],
    }


def make_service(*, hits=None, raw_text="full text", existing_brief=None):
    paper_repo = MagicMock()
    paper_repo.get_by_arxiv_id.return_value = SimpleNamespace(raw_text=raw_text, pdf_url=f"https://arxiv.org/pdf/{ARXIV_ID}.pdf")
    brief_repo = MagicMock()
    brief_repo.get_compatible.return_value = existing_brief
    opensearch = MagicMock()
    opensearch.get_chunks_by_paper.return_value = [{"chunk_id": "probe"}]
    opensearch.search_unified.return_value = {
        "hits": hits if hits is not None else [{
            "arxiv_id": ARXIV_ID, "chunk_id": "chunk-1", "section_title": "Method", "chunk_text": EXCERPT,
        }]
    }
    embeddings = MagicMock()
    embeddings.embed_query = AsyncMock(return_value=[0.1, 0.2])
    ollama = MagicMock()
    ollama.generate = AsyncMock(return_value={"response": json.dumps(generated_brief())})
    settings = SimpleNamespace(deep_dive=SimpleNamespace(max_chunks=10, max_prompt_chars=12000, max_chunk_chars=5000))
    service = PaperDeepDiveService(paper_repo, brief_repo, opensearch, embeddings, ollama, settings)
    return service, paper_repo, brief_repo, opensearch, embeddings, ollama


@pytest.mark.asyncio
async def test_retrieval_and_generation_are_exact_paper_scoped_and_structured():
    service, _, brief_repo, opensearch, embeddings, ollama = make_service()

    result = await service.generate(
        ARXIV_ID, PaperDeepDiveRequest(model="model-x", top_k=4, use_hybrid=True)
    )

    assert opensearch.search_unified.call_args.kwargs["arxiv_id"] == ARXIV_ID
    assert opensearch.search_unified.call_args.kwargs["size"] == 4
    assert opensearch.search_unified.call_args.kwargs["use_hybrid"] is True
    embeddings.embed_query.assert_awaited_once()
    assert ollama.generate.call_args.kwargs["model"] == "model-x"
    assert ollama.generate.call_args.kwargs["format"]
    assert result.retrieval_mode == "hybrid"
    assert result.brief.evidence_references[0].chunk_id == "chunk-1"
    assert result.brief.evidence_references[0].excerpt == EXCERPT
    assert result.brief.experimental_results.startswith("Unavailable")
    assert result.prompt_version == PROMPT_VERSION and result.cached is False
    cache_key = brief_repo.get_compatible.call_args.kwargs
    assert cache_key["arxiv_id"] == ARXIV_ID
    assert cache_key["model"] == "model-x"
    assert cache_key["prompt_version"] == PROMPT_VERSION
    assert cache_key["retrieval_mode"] == "hybrid" and cache_key["top_k"] == 4
    assert len(cache_key["evidence_hash"]) == 64
    brief_repo.save.assert_called_once()


@pytest.mark.asyncio
async def test_foreign_search_hits_are_discarded_and_no_global_fallback_occurs():
    service, _, brief_repo, opensearch, _, ollama = make_service(hits=[{
        "arxiv_id": "1801.00001v1", "chunk_id": "foreign", "chunk_text": "other paper evidence",
    }])

    with pytest.raises(PaperDeepDiveInsufficientEvidenceError):
        await service.generate(ARXIV_ID, PaperDeepDiveRequest(use_hybrid=False))

    assert opensearch.search_unified.call_args.kwargs["arxiv_id"] == ARXIV_ID
    assert opensearch.search_unified.call_args.kwargs["use_hybrid"] is False
    ollama.generate.assert_not_awaited()
    brief_repo.save.assert_not_called()


@pytest.mark.asyncio
async def test_invalid_references_are_removed_and_unknown_fields_remain_explicit():
    service, _, _, _, _, ollama = make_service()
    ollama.generate.return_value = {"response": json.dumps(generated_brief(valid_ref=False))}

    result = await service.generate(ARXIV_ID, PaperDeepDiveRequest(use_hybrid=False))

    assert result.brief.evidence_references == []
    assert any("removed" in gap for gap in result.brief.information_gaps)
    assert any("No valid supporting" in gap for gap in result.brief.information_gaps)
    assert result.brief.experimental_results.startswith("Unavailable")
    assert result.brief.implementation_details.startswith("Unavailable")


@pytest.mark.asyncio
async def test_compatible_stored_brief_is_reused_without_generation():
    stored = SimpleNamespace(content=generated_brief())
    service, _, brief_repo, _, _, ollama = make_service(existing_brief=stored)

    result = await service.generate(ARXIV_ID, PaperDeepDiveRequest(use_hybrid=False))

    assert result.cached is True
    ollama.generate.assert_not_awaited()
    brief_repo.save.assert_not_called()


@pytest.mark.asyncio
async def test_generation_failure_is_not_persisted():
    service, _, brief_repo, _, _, ollama = make_service()
    ollama.generate.side_effect = RuntimeError("offline")

    with pytest.raises(PaperDeepDiveGenerationUnavailableError):
        await service.generate(ARXIV_ID, PaperDeepDiveRequest(use_hybrid=False))

    brief_repo.save.assert_not_called()


@pytest.mark.asyncio
async def test_missing_and_unprepared_papers_are_distinct():
    missing, repo, *_ = make_service()
    repo.get_by_arxiv_id.return_value = None
    with pytest.raises(PaperDeepDiveNotFoundError):
        await missing.generate(ARXIV_ID, PaperDeepDiveRequest())

    unprepared, repo, *_ = make_service(raw_text=None)
    with pytest.raises(PaperDeepDiveNotPreparedError):
        await unprepared.generate(ARXIV_ID, PaperDeepDiveRequest())
