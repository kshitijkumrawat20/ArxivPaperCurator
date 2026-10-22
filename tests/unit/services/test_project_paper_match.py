from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from src.schema.api.project_match import ProjectMatchRequest
from src.services.project_paper_match import (
    MAX_ABSTRACT_CHARS,
    MAX_SEARCH_QUERY_CHARS,
    ProjectMatchSearchUnavailableError,
    ProjectPaperMatchService,
)


def hit(arxiv_id="1706.03762v7", **overrides):
    paper = {
        "arxiv_id": arxiv_id,
        "title": "Attention Is All You Need",
        "abstract": "We propose a transformer architecture using attention over learned representations.",
        "authors": ["A. Author", "B. Author"],
        "categories": ["cs.CL", "cs.AI"],
        "published_date": "2017-06-12T00:00:00+00:00",
        "pdf_url": f"https://arxiv.org/pdf/{arxiv_id}.pdf",
        "source_url": f"https://arxiv.org/pdf/{arxiv_id}.pdf",
        "score": 8.1,
    }
    paper.update(overrides)
    return paper


def request(**overrides):
    return ProjectMatchRequest(
        project_description="Build a transformer-based retrieval system for scientific papers.",
        technologies=["PyTorch", "vector search"],
        research_interests=["attention mechanisms"],
        **overrides,
    )


def test_request_validation_defaults_normalization_and_date_range():
    normalized = ProjectMatchRequest(project_description="  Train a retrieval model  ")
    assert normalized.project_description == "Train a retrieval model"
    assert normalized.top_k == 10
    assert normalized.technologies == [] and normalized.categories == []

    with pytest.raises(ValidationError, match="date_from must be on or before date_to"):
        request(date_from=date(2025, 1, 1), date_to=date(2024, 1, 1))
    with pytest.raises(ValidationError):
        ProjectMatchRequest(project_description="   ")
    with pytest.raises(ValidationError):
        ProjectMatchRequest(project_description="valid", top_k=21)
    with pytest.raises(ValidationError):
        ProjectMatchRequest(project_description="long " * 500)
    with pytest.raises(ValidationError):
        ProjectMatchRequest(project_description="valid", categories=["not a valid category!"])


def test_metadata_search_ranks_exact_versions_and_returns_only_grounded_signals():
    opensearch = MagicMock()
    opensearch.search_paper_metadata.return_value = {
        "hits": {
            "total": {"value": 2},
            "hits": [
                {"_score": 8.1, "_source": hit()},
                {"_score": 6.4, "_source": hit("1706.03762v6", title="Older Attention Version")},
            ],
        }
    }
    service = ProjectPaperMatchService(opensearch)

    result = service.match(request(project_title="Citation aware paper retrieval"))

    assert [paper.arxiv_id for paper in result.papers] == ["1706.03762v7", "1706.03762v6"]
    assert [paper.retrieval_rank for paper in result.papers] == [1, 2]
    assert result.papers[0].search_score == 8.1
    assert result.score_semantics.endswith("not a calibrated probability")
    signals = result.papers[0].match_signals
    assert any(signal.term == "PyTorch" and signal.source_field == "abstract" for signal in signals) is False
    assert any(signal.term == "attention mechanisms" and signal.source_field == "abstract" for signal in signals) is False
    assert any(signal.term.casefold() == "attention" for signal in signals)
    assert any(signal.term == "transformer" and signal.source_field == "abstract" for signal in signals)
    assert all(signal.evidence_excerpt in (
        result.papers[0].title, result.papers[0].abstract_excerpt, *result.papers[0].categories
    ) or signal.evidence_excerpt.startswith("…") for signal in signals)
    assert result.papers[0].abstract_excerpt == hit()["abstract"][:MAX_ABSTRACT_CHARS]
    assert result.query_context.search_query


def test_category_and_date_filters_are_part_of_metadata_query_and_no_full_text_path_is_used():
    opensearch = MagicMock()
    opensearch.search_paper_metadata.return_value = {"hits": {"total": {"value": 1}, "hits": [{"_score": 2.0, "_source": hit()}]}}
    service = ProjectPaperMatchService(opensearch)

    result = service.match(request(
        categories=["cs.AI"], date_from=date(2017, 1, 1), date_to=date(2020, 12, 31), top_k=4
    ))

    body = opensearch.search_paper_metadata.call_args.args[0]
    assert body["size"] == 4
    assert {"terms": {"categories": ["cs.AI"]}} in body["query"]["bool"]["filter"]
    assert {"range": {"published_date": {"gte": "2017-01-01", "lt": "2021-01-01"}}} in body["query"]["bool"]["filter"]
    assert result.papers[0].arxiv_id == "1706.03762v7"
    # The service only calls the metadata-index interface; no parser, embedding,
    # chunk retrieval, or LLM service is constructed or triggered.
    opensearch.search_paper_metadata.assert_called_once()


def test_metadata_only_empty_results_and_search_failure():
    opensearch = MagicMock()
    opensearch.search_paper_metadata.return_value = {"hits": {"total": {"value": 0}, "hits": []}}
    result = ProjectPaperMatchService(opensearch).match(request())
    assert result.result_count == 0 and result.papers == []
    assert "No papers matched" in result.message

    opensearch.search_paper_metadata.side_effect = RuntimeError("internal connection detail")
    with pytest.raises(ProjectMatchSearchUnavailableError, match="Metadata search is unavailable"):
        ProjectPaperMatchService(opensearch).match(request())


def test_query_and_response_are_bounded_and_route_is_declared_before_dynamic_detail_route():
    long_request = ProjectMatchRequest(project_description="retrieval " * 190)
    opensearch = MagicMock()
    opensearch.search_paper_metadata.return_value = {"hits": {"total": 0, "hits": []}}
    result = ProjectPaperMatchService(opensearch).match(long_request)
    assert len(result.query_context.search_query) <= MAX_SEARCH_QUERY_CHARS
    assert result.query_context.search_query == opensearch.search_paper_metadata.call_args.args[0]["query"]["bool"]["must"][0]["multi_match"]["query"]

    source = Path("src/routers/paper.py").read_text(encoding="utf-8")
    assert source.index('@router.post("/match-project"') < source.index('@router.get("/{arxiv_id}"')
    main_source = Path("src/main.py").read_text(encoding="utf-8")
    assert 'app.include_router(paper.router, prefix="/api/v1")' in main_source
