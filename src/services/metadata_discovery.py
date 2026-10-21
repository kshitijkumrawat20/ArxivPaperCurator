"""BM25 query construction and paper metadata discovery."""

from datetime import date, timedelta
from typing import Any, Optional


def build_metadata_search_query(
    query: str = "",
    size: int = 10,
    from_: int = 0,
    categories: Optional[list[str]] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
) -> dict[str, Any]:
    must = []
    if query.strip():
        must.append({"multi_match": {"query": query.strip(), "fields": ["title^3", "abstract^2", "authors"], "type": "best_fields"}})
    else:
        must.append({"match_all": {}})
    filters = []
    if categories:
        filters.append({"terms": {"categories": categories}})
    published_range = {}
    if date_from:
        published_range["gte"] = date_from.isoformat()
    if date_to:
        # Use an exclusive next-day bound so date_to includes the whole date even
        # though indexed publication values are timestamps.
        published_range["lt"] = (date_to + timedelta(days=1)).isoformat()
    if published_range:
        filters.append({"range": {"published_date": published_range}})
    bool_query: dict[str, Any] = {"must": must}
    if filters:
        bool_query["filter"] = filters
    return {
        "query": {"bool": bool_query},
        "size": size,
        "from": from_,
        "track_total_hits": True,
        "sort": [{"published_date": {"order": "desc"}}, {"arxiv_id": {"order": "asc"}}],
        "_source": ["arxiv_id", "title", "abstract", "authors", "categories", "published_date", "pdf_url"],
    }


class MetadataDiscoveryService:
    def __init__(self, opensearch_client: Any):
        self.opensearch_client = opensearch_client

    def search(self, **filters: Any) -> dict[str, Any]:
        body = build_metadata_search_query(**filters)
        response = self.opensearch_client.search_paper_metadata(body)
        hits_response = response.get("hits", {})
        total_data = hits_response.get("total", 0)
        total = total_data.get("value", 0) if isinstance(total_data, dict) else total_data
        hits = []
        for hit in hits_response.get("hits", []):
            source = dict(hit.get("_source", {}))
            source["score"] = hit.get("_score")
            source["source_url"] = source.get("pdf_url")
            hits.append(source)
        return {"total": total, "hits": hits}
