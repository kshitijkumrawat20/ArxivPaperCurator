import pytest
from src.services.opensearch.query_builder import QueryBuilder 

def test_query_builder_basic_query():
    """Test basic query construction."""

    builder = QueryBuilder(query="machine learning", size = 5)
    query = builder.build()

    assert query["size"] == 5
    assert query["from"] == 0
    assert query["track_total_hits"] is True

    bool_query = query["query"]["bool"]
    assert len(bool_query["must"]) == 1

    multi_match = bool_query["must"][0]["multi_match"]
    assert multi_match["query"] == "machine learning"
    assert "title^3" in multi_match["fields"]
    assert "abstract^2" in multi_match["fields"]
    assert "authors^1" in multi_match["fields"]
    