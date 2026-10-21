from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.services.metadata_discovery import MetadataDiscoveryService, build_metadata_search_query
from src.services.metadata_indexing import (
    MetadataIndexingService,
    build_metadata_document,
    build_metadata_index_action,
)


def paper(**overrides):
    data = {
        "arxiv_id": "1706.03762v7",
        "title": "Attention Is All You Need",
        "abstract": "We propose a transformer.",
        "authors": ["A. Author", "B. Author"],
        "categories": ["cs.CL", "cs.LG"],
        "published_date": datetime(2017, 6, 12, tzinfo=timezone.utc),
        "pdf_url": "https://arxiv.org/pdf/1706.03762v7",
        "updated_at": datetime(2025, 1, 1, tzinfo=timezone.utc),
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def test_metadata_document_contains_version_and_metadata_without_embeddings():
    document = build_metadata_document(paper())
    assert document["arxiv_id"] == "1706.03762v7"
    assert document["published_date"].startswith("2017-06-12")
    assert document["updated_at"].startswith("2025-01-01")
    assert "embedding" not in document


def test_bulk_document_id_is_exact_versioned_arxiv_id():
    action = build_metadata_index_action(paper(), "papers-metadata")
    assert action["_id"] == "1706.03762v7"
    assert action["_index"] == "papers-metadata"
    assert action["_source"]["arxiv_id"] == action["_id"]


def test_single_metadata_indexing_uses_deterministic_id_for_upserts():
    opensearch = MagicMock()
    opensearch.index_paper_metadata.side_effect = [True, True]
    service = MetadataIndexingService(opensearch)

    assert service.index_paper(paper(title="First title"))
    assert service.index_paper(paper(title="Updated title"))
    assert not hasattr(service, "pdf_parser")
    assert not hasattr(service, "embeddings_client")
    assert not hasattr(service, "llm_client")
    assert opensearch.index_paper_metadata.call_args_list[0].args[0].title == "First title"
    assert opensearch.index_paper_metadata.call_args_list[1].args[0].title == "Updated title"


def test_batch_indexing_enforces_batch_limit_and_reports_success_failure_counts():
    opensearch = MagicMock()
    opensearch.bulk_index_paper_metadata.return_value = {"success": 1, "failed": 1, "errors": [{"index": {}}]}
    service = MetadataIndexingService(opensearch, batch_size=2)

    assert service.index_batch([paper(), paper(arxiv_id="2401.00001")])["failed"] == 1
    with pytest.raises(ValueError, match="Batch contains"):
        service.index_batch([paper(), paper(), paper()])


def test_bm25_search_query_builds_category_date_filters_and_newest_pagination():
    body = build_metadata_search_query(
        "transformer", size=7, from_=14, categories=["cs.AI", "cs.LG"],
        date_from=date(2020, 1, 1), date_to=date(2024, 12, 31),
    )
    assert body["size"] == 7 and body["from"] == 14
    assert body["sort"][0] == {"published_date": {"order": "desc"}}
    query = body["query"]["bool"]
    assert query["must"][0]["multi_match"]["fields"] == ["title^3", "abstract^2", "authors"]
    assert {"terms": {"categories": ["cs.AI", "cs.LG"]}} in query["filter"]
    assert {"range": {"published_date": {"gte": "2020-01-01", "lt": "2025-01-01"}}} in query["filter"]


def test_empty_query_matches_all_and_discovery_serializes_source_url():
    opensearch = MagicMock()
    opensearch.search_paper_metadata.return_value = {
        "hits": {"total": {"value": 1}, "hits": [{"_score": 1.2, "_source": build_metadata_document(paper())}]}
    }
    result = MetadataDiscoveryService(opensearch).search(query="", size=10, from_=0)
    body = opensearch.search_paper_metadata.call_args.args[0]
    assert body["query"]["bool"]["must"] == [{"match_all": {}}]
    assert result["hits"][0]["source_url"] == result["hits"][0]["pdf_url"]
    assert result["total"] == 1
