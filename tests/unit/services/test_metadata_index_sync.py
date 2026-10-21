from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

from src.services.metadata_index_sync import MetadataIndexSyncService


class MemoryDatabase:
    def __init__(self):
        self.checkpoints = {}
        self.papers = [SimpleNamespace(arxiv_id=f"2401.0000{i}") for i in range(1, 6)]

    @contextmanager
    def get_session(self):
        yield object()


class Checkpoints:
    def __init__(self, session, db):
        self.db = db

    def get(self, job_id):
        item = self.db.checkpoints.get(job_id)
        return deepcopy(item) if item else None

    def create(self, checkpoint):
        self.db.checkpoints[checkpoint.job_id] = deepcopy(checkpoint)
        return deepcopy(checkpoint)

    def save(self, checkpoint):
        self.db.checkpoints[checkpoint.job_id] = deepcopy(checkpoint)
        return deepcopy(checkpoint)


class Papers:
    def __init__(self, session, db):
        self.db = db

    def get_metadata_batch_after(self, last_id, limit):
        rows = [paper for paper in self.db.papers if last_id is None or paper.arxiv_id > last_id]
        return rows[:limit]


def make_service(db, opensearch):
    return MetadataIndexSyncService(
        db,
        opensearch,
        paper_repository_factory=lambda session: Papers(session, db),
        checkpoint_repository_factory=lambda session: Checkpoints(session, db),
    )


def test_sync_is_bounded_and_resumes_from_saved_keyset_cursor():
    db = MemoryDatabase()
    opensearch = MagicMock()
    opensearch.bulk_index_paper_metadata.side_effect = [
        {"success": 2, "failed": 0, "errors": []},
        {"success": 2, "failed": 0, "errors": []},
        {"success": 1, "failed": 0, "errors": []},
    ]
    service = make_service(db, opensearch)

    first = service.run("sync-v1", batch_size=2, max_batches=1)
    assert first["status"] == "paused"
    assert first["last_arxiv_id"] == "2401.00002"
    assert first["records_attempted"] == 2

    second = service.run("sync-v1", batch_size=2, max_batches=5)
    assert second["status"] == "completed"
    assert second["records_indexed"] == 5
    assert opensearch.bulk_index_paper_metadata.call_count == 3


def test_partial_bulk_failure_keeps_cursor_for_idempotent_retry():
    db = MemoryDatabase()
    opensearch = MagicMock()
    opensearch.bulk_index_paper_metadata.side_effect = [
        {"success": 1, "failed": 1, "errors": [{"index": {}}]},
        {"success": 2, "failed": 0, "errors": []},
    ]
    service = make_service(db, opensearch)

    failed = service.run("retry-v1", batch_size=2, max_batches=1)
    assert failed["status"] == "failed"
    assert failed["last_arxiv_id"] is None

    resumed = service.run("retry-v1", batch_size=2, max_batches=1)
    assert resumed["status"] == "paused"
    assert resumed["last_arxiv_id"] == "2401.00002"
    first_attempt = opensearch.bulk_index_paper_metadata.call_args_list[0].args[0]
    retry_attempt = opensearch.bulk_index_paper_metadata.call_args_list[1].args[0]
    assert [item.arxiv_id for item in first_attempt] == [item.arxiv_id for item in retry_attempt]
