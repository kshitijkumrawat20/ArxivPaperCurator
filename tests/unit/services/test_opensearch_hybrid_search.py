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
        arxiv_id="1706.03762v7",
    )

    body = client.client.search.call_args.kwargs["body"]
    lexical_query, vector_query = body["query"]["hybrid"]["queries"]

    assert body["size"] == 5
    assert body["from"] == 10
    assert body["min_score"] == 0.0
    expected_filters = [
        {"terms": {"categories": ["cs.CV", "cs.AI"]}},
        {"term": {"arxiv_id": "1706.03762v7"}},
    ]
    assert lexical_query["bool"]["filter"] == expected_filters
    assert vector_query["bool"]["filter"] == expected_filters
    assert vector_query["bool"]["must"][0]["knn"]["embedding"]["k"] == 30
    assert result == {"total": 37, "hits": []}


def test_bm25_and_vector_search_accept_exact_paper_filter():
    client = OpenSearchClient.__new__(OpenSearchClient)
    client.index_name = "papers-chunks"
    client.client = MagicMock()
    client.client.search.return_value = {"hits": {"total": {"value": 0}, "hits": []}}

    client.search_unified(query="method", size=4, use_hybrid=False, arxiv_id="1706.03762v7")
    bm25_body = client.client.search.call_args.kwargs["body"]
    assert {"term": {"arxiv_id": "1706.03762v7"}} in bm25_body["query"]["bool"]["filter"]

    client.search_chunks_vector([0.1, 0.2], size=4, arxiv_id="1706.03762v7")
    vector_body = client.client.search.call_args.kwargs["body"]
    assert vector_body["query"]["bool"]["filter"] == [{"term": {"arxiv_id": "1706.03762v7"}}]
