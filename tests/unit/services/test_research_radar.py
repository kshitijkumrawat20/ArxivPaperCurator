from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from src.schema.api.research_radar import ResearchRadarRequest
from src.services.research_radar import (
    MAX_ABSTRACT_CHARS,
    RRF_K,
    ResearchRadarService,
    ResearchRadarUnavailableError,
)


def hit(arxiv_id="2401.00001v2", **overrides):
    data = {
        "arxiv_id": arxiv_id,
        "title": "Graph neural networks for scientific discovery",
        "abstract": "We study graph neural networks for scientific discovery.",
        "authors": ["A. Researcher"],
        "categories": ["cs.LG", "cs.AI"],
        "published_date": "2025-06-10T00:00:00+00:00",
        "pdf_url": f"https://arxiv.org/pdf/{arxiv_id}.pdf",
        "source_url": f"https://arxiv.org/pdf/{arxiv_id}.pdf",
        "score": 0.01,
    }
    data.update(overrides)
    return data


def request(**overrides):
    return ResearchRadarRequest(topics=[" graph neural networks ", "retrieval augmented generation"], **overrides)


def test_request_normalizes_topics_removes_duplicates_and_validates_bounds():
    normalized = ResearchRadarRequest(
        topics=["  graph   neural networks ", "GRAPH neural networks", " retrieval "]
    )
    assert normalized.topics == ["graph neural networks", "retrieval"]
    assert normalized.lookback_days == 30
    assert normalized.top_k == 10
    assert normalized.per_topic_candidate_limit == 20

    with pytest.raises(ValidationError):
        ResearchRadarRequest(topics=[])
    with pytest.raises(ValidationError):
        ResearchRadarRequest(topics=[" "])
    with pytest.raises(ValidationError):
        ResearchRadarRequest(topics=["x" * 121])
    with pytest.raises(ValidationError):
        ResearchRadarRequest(topics=["topic"], lookback_days=366)
    with pytest.raises(ValidationError):
        ResearchRadarRequest(topics=["topic"], top_k=21)
    with pytest.raises(ValidationError):
        ResearchRadarRequest(topics=["topic"], per_topic_candidate_limit=51)
    with pytest.raises(ValidationError):
        ResearchRadarRequest(topics=["x" * 101, "y" * 101, "z" * 101, "w" * 101, "q" * 101])


def test_every_topic_search_has_same_in_query_date_and_category_filters():
    client = MagicMock()
    client.search_paper_metadata.return_value = {"hits": {"total": {"value": 0}, "hits": []}}
    service = ResearchRadarService(client, today_provider=lambda: date(2025, 6, 30))

    result = service.search(request(categories=["cs.AI"], lookback_days=7))

    assert result.date_window.start_date == date(2025, 6, 24)
    assert result.date_window.end_date == date(2025, 6, 30)
    assert client.search_paper_metadata.call_count == 2
    for call in client.search_paper_metadata.call_args_list:
        body = call.args[0]
        assert body["size"] == 20 and body["from"] == 0
        filters = body["query"]["bool"]["filter"]
        assert {"terms": {"categories": ["cs.AI"]}} in filters
        assert {"range": {"published_date": {"gte": "2025-06-24", "lt": "2025-07-01"}}} in filters
    assert result.result_count == 0
    assert "No papers matched" in result.message


def test_rrf_ignores_bm25_scale_deduplicates_exact_ids_and_keeps_versions_distinct():
    client = MagicMock()
    replies = [
        {"hits": {"total": 3, "hits": [
            {"_score": 0.00001, "_source": hit("2401.00001v2")},
            {"_score": 999999.0, "_source": hit("2401.00002v1", title="A second retrieval paper")},
            {"_score": 0.000001, "_source": hit("2401.00001v1", title="Graph neural networks earlier version")},
        ]}},
        {"hits": {"total": 3, "hits": [
            {"_score": 1000000.0, "_source": hit("2401.00001v2")},
            {"_score": 0.0000001, "_source": hit("2401.00002v1", title="A second retrieval paper")},
            {"_score": 2.0, "_source": hit("2401.00001v1", title="Graph neural networks earlier version")},
        ]}},
    ]
    client.search_paper_metadata.side_effect = replies
    service = ResearchRadarService(client, today_provider=lambda: date(2025, 6, 30))

    result = service.search(request())

    assert [paper.arxiv_id for paper in result.papers] == [
        "2401.00001v2", "2401.00002v1", "2401.00001v1"
    ]
    expected_top_score = 1 / (RRF_K + 1) + 1 / (RRF_K + 1)
    assert result.papers[0].fusion_score == pytest.approx(expected_top_score)
    assert result.papers[0].matched_topics == request().topics
    assert result.papers[0].overall_rank == 1
    assert "not probability" in result.fusion_method
    assert result.total_candidates == 3
    # Signals cite literal evidence from retrieved metadata, not generated prose.
    signal = next(signal for signal in result.papers[0].match_signals if signal.topic == "graph neural networks")
    assert signal.source_field == "title"
    assert "graph neural networks" in signal.evidence_excerpt.casefold()
    assert all(paper.match_signals for paper in result.papers)


def test_partial_failure_is_reported_and_successful_topic_results_are_returned():
    client = MagicMock()
    client.search_paper_metadata.side_effect = [
        RuntimeError("private connection detail"),
        {"hits": {"total": 1, "hits": [{"_score": 5.0, "_source": hit()}]}},
    ]
    service = ResearchRadarService(client, today_provider=lambda: date(2025, 6, 30))

    result = service.search(request())

    assert result.result_count == 1
    assert [warning.topic for warning in result.warnings] == ["graph neural networks"]
    assert "private connection detail" not in result.warnings[0].message
    assert result.papers[0].matched_topics == ["retrieval augmented generation"]


def test_all_searches_failing_returns_service_error_and_empty_success_is_not_failure():
    client = MagicMock()
    client.search_paper_metadata.side_effect = RuntimeError("unavailable")
    service = ResearchRadarService(client, today_provider=lambda: date(2025, 6, 30))
    with pytest.raises(ResearchRadarUnavailableError):
        service.search(request())

    client.search_paper_metadata.side_effect = None
    client.search_paper_metadata.return_value = {"hits": {"total": 0, "hits": []}}
    empty = service.search(request())
    assert empty.result_count == 0 and empty.papers == []
    assert empty.warnings == []


def test_metadata_only_response_fields_and_content_are_bounded_and_route_is_static():
    client = MagicMock()
    client.search_paper_metadata.return_value = {
        "hits": {"total": 1, "hits": [{"_score": 4.2, "_source": hit(abstract="evidence " * 500)}]}
    }
    result = ResearchRadarService(client, today_provider=lambda: date(2025, 6, 30)).search(
        ResearchRadarRequest(topics=["graph neural networks"])
    )
    paper = result.papers[0]
    assert len(paper.abstract_excerpt) == MAX_ABSTRACT_CHARS
    assert paper.arxiv_id == "2401.00001v2"
    assert paper.pdf_url and paper.source_url
    assert not hasattr(paper, "embedding") and not hasattr(paper, "chunks")

    source = Path("src/routers/paper.py").read_text(encoding="utf-8")
    assert source.index('@router.post("/radar"') < source.index('@router.get("/{arxiv_id}"')
