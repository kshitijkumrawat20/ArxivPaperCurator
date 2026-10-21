from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from src.routers.paper import discover_papers


def test_discovery_route_serializes_paper_result_and_filters():
    opensearch = MagicMock()
    opensearch.search_paper_metadata.return_value = {
        "hits": {"total": {"value": 1}, "hits": [{"_score": 2.0, "_source": {
            "arxiv_id": "2401.00001v2", "title": "A title", "abstract": "An abstract",
            "authors": ["A Author"], "categories": ["cs.AI"], "published_date": "2024-01-01T00:00:00Z",
            "pdf_url": "https://arxiv.org/pdf/2401.00001v2", "updated_at": "2024-02-01T00:00:00Z",
        }}]},
    }
    response = discover_papers(
        opensearch, query="model", categories=["cs.AI"], date_from=date(2020, 1, 1),
        date_to=date(2025, 1, 1), size=5, offset=10,
    )
    assert response.model_dump(by_alias=True)["from"] == 10
    assert response.papers[0].source_url == "https://arxiv.org/pdf/2401.00001v2"
    assert response.papers[0].authors == ["A Author"]


def test_discovery_route_returns_clear_503_when_opensearch_is_unavailable():
    opensearch = MagicMock()
    opensearch.search_paper_metadata.side_effect = ConnectionError("offline")
    with pytest.raises(HTTPException) as error:
        discover_papers(opensearch, query="paper")
    assert error.value.status_code == 503
    assert "unavailable" in error.value.detail
