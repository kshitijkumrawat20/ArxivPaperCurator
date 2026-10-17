from unittest.mock import MagicMock

from src.services.opensearch.client import OpenSearchClient


def test_hybrid_search_filters_both_branches_and_preserves_offset():
    client = OpenSearchClient.__new__(OpenSearchClient)
    client.index_name = "papers-chunks"
    client.client = MagicMock()
    client.client.search.return_value = {
        "hits": {"total": {"value": 37}, "hits": []}
    }

    result = client.search_unified(
        query="vision transformer",
        query_embedding=[0.1, 0.2],
        size=5,
        from_=10,
        categories=["cs.CV", "cs.AI"],
        use_hybrid=True,
    )

    body = client.client.search.call_args.kwargs["body"]
    lexical_query, vector_query = body["query"]["hybrid"]["queries"]

    assert body["size"] == 5
    assert body["from"] == 10
    assert body["min_score"] == 0.0
    assert lexical_query["bool"]["filter"] == [{"terms": {"categories": ["cs.CV", "cs.AI"]}}]
    assert vector_query["bool"]["filter"] == [{"terms": {"categories": ["cs.CV", "cs.AI"]}}]
    assert vector_query["bool"]["must"][0]["knn"]["embedding"]["k"] == 30
    assert result == {"total": 37, "hits": []}
