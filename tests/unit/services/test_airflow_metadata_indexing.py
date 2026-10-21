from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from airflow.dags.arxiv_ingestion import indexing


def test_daily_metadata_task_sends_database_metadata_to_index_without_pdf_pipeline():
    paper = SimpleNamespace(
        arxiv_id="2501.00001", title="Metadata only", abstract="Abstract", authors=["A Author"],
        categories=["cs.AI"], published_date="2025-01-01", pdf_url="https://arxiv.org/pdf/2501.00001",
        updated_at="2025-01-02",
    )
    database = MagicMock()
    session = MagicMock()
    database.get_session.return_value.__enter__.return_value = session
    ti = MagicMock()
    ti.xcom_pull.return_value = {"arxiv_ids": [paper.arxiv_id]}
    opensearch = MagicMock()
    opensearch.bulk_index_paper_metadata.return_value = {"success": 1, "failed": 0, "errors": []}

    with (
        patch.object(indexing, "make_database", return_value=database),
        patch.object(indexing, "make_opensearch_client_fresh", return_value=opensearch),
        patch("src.respositories.paper.PaperRepository.get_by_arxiv_ids", return_value=[paper]),
    ):
        result = indexing.index_papers_metadata(ti=ti)

    assert result == {"papers_indexed": 1, "papers_failed": 0}
    indexed = opensearch.bulk_index_paper_metadata.call_args.args[0][0]
    assert indexed.arxiv_id == paper.arxiv_id
    database.teardown.assert_called_once()
