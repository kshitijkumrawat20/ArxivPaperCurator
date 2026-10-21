"""Vector-free indexing of paper metadata into the paper discovery index."""

from datetime import date, datetime
from typing import Any, Iterable


def _value(paper: Any, key: str, default: Any = None) -> Any:
    if isinstance(paper, dict):
        return paper.get(key, default)
    return getattr(paper, key, default)


def _iso(value: Any) -> Any:
    return value.isoformat() if isinstance(value, (date, datetime)) else value


def build_metadata_document(paper: Any) -> dict[str, Any]:
    """Convert a SQLAlchemy paper or mapping into the strict OpenSearch shape."""
    arxiv_id = _value(paper, "arxiv_id")
    if not arxiv_id:
        raise ValueError("Metadata document requires arxiv_id")
    return {
        "arxiv_id": str(arxiv_id),
        "title": _value(paper, "title") or "",
        "abstract": _value(paper, "abstract") or "",
        "authors": list(_value(paper, "authors") or []),
        "categories": list(_value(paper, "categories") or []),
        "published_date": _iso(_value(paper, "published_date")),
        "pdf_url": _value(paper, "pdf_url") or "",
        "updated_at": _iso(_value(paper, "updated_at")),
    }


def build_metadata_index_action(paper: Any, index_name: str) -> dict[str, Any]:
    """Build a deterministic OpenSearch bulk upsert action."""
    document = build_metadata_document(paper)
    return {"_op_type": "index", "_index": index_name, "_id": document["arxiv_id"], "_source": document}


class MetadataIndexingService:
    """Reusable bounded wrapper for metadata-only OpenSearch writes."""

    def __init__(self, opensearch_client: Any, batch_size: int = 100, max_batch_size: int = 500):
        if not 1 <= batch_size <= max_batch_size:
            raise ValueError(f"batch_size must be between 1 and {max_batch_size}")
        self.opensearch_client = opensearch_client
        self.batch_size = batch_size
        self.max_batch_size = max_batch_size

    def index_paper(self, paper: Any) -> bool:
        return self.opensearch_client.index_paper_metadata(paper)

    def index_batch(self, papers: Iterable[Any]) -> dict[str, Any]:
        records = list(papers)
        if len(records) > self.batch_size:
            raise ValueError(f"Batch contains {len(records)} records; configured limit is {self.batch_size}")
        if not records:
            return {"success": 0, "failed": 0, "errors": []}
        return self.opensearch_client.bulk_index_paper_metadata(records)
