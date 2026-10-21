"""Manually run, bounded and resumable PostgreSQL metadata index synchronization."""

from datetime import datetime, timezone
from typing import Any

from src.models.historical_backfill import MetadataIndexSyncCheckpoint
from src.respositories.backfill_checkpoint import MetadataIndexSyncCheckpointRepository
from src.respositories.paper import PaperRepository
from src.services.metadata_indexing import MetadataIndexingService

MAX_SYNC_BATCH_SIZE = 500
MAX_BATCHES_PER_RUN = 100


class MetadataIndexSyncService:
    def __init__(
        self, database: Any, opensearch_client: Any, paper_repository_factory: Any = PaperRepository,
        checkpoint_repository_factory: Any = MetadataIndexSyncCheckpointRepository,
    ):
        self.database = database
        self.indexing = MetadataIndexingService(opensearch_client, batch_size=MAX_SYNC_BATCH_SIZE)
        self.paper_repository_factory = paper_repository_factory
        self.checkpoint_repository_factory = checkpoint_repository_factory

    def run(self, job_id: str, batch_size: int = 100, max_batches: int = 5) -> dict[str, Any]:
        if not job_id or len(job_id) > 160:
            raise ValueError("job_id must be a non-empty string of at most 160 characters")
        if not 1 <= batch_size <= MAX_SYNC_BATCH_SIZE:
            raise ValueError(f"batch_size must be between 1 and {MAX_SYNC_BATCH_SIZE}")
        if not 1 <= max_batches <= MAX_BATCHES_PER_RUN:
            raise ValueError(f"max_batches must be between 1 and {MAX_BATCHES_PER_RUN}")

        checkpoint = self._load_or_create(job_id)
        if checkpoint.status == "completed":
            return self._summary(checkpoint, 0, 0)
        checkpoint.status = "running"
        checkpoint.last_error = None
        self._save(checkpoint)
        batches_processed = records_attempted = 0

        while batches_processed < max_batches:
            try:
                with self.database.get_session() as session:
                    papers = self.paper_repository_factory(session).get_metadata_batch_after(
                        checkpoint.last_arxiv_id, batch_size
                    )
                if not papers:
                    checkpoint.status = "completed"
                    self._save(checkpoint)
                    break

                result = self.indexing.index_batch(papers)
                records_attempted += len(papers)
                batches_processed += 1
                if result["failed"]:
                    # Keep the old cursor. Successfully indexed docs will be safely
                    # overwritten on retry because IDs are deterministic.
                    checkpoint.status = "failed"
                    checkpoint.last_error = f"{result['failed']} metadata document(s) failed; batch will be retried"
                    self._save(checkpoint)
                    break

                checkpoint.last_arxiv_id = papers[-1].arxiv_id
                checkpoint.records_indexed += result["success"]
                checkpoint.status = "running"
                self._save(checkpoint)
                if len(papers) < batch_size:
                    checkpoint.status = "completed"
                    self._save(checkpoint)
                    break
            except Exception as exc:
                checkpoint.status = "failed"
                checkpoint.last_error = f"{type(exc).__name__}; current batch will be retried"
                self._save(checkpoint)
                break
        else:
            checkpoint.status = "paused"
            self._save(checkpoint)
        return self._summary(checkpoint, batches_processed, records_attempted)

    def _load_or_create(self, job_id: str) -> MetadataIndexSyncCheckpoint:
        with self.database.get_session() as session:
            repository = self.checkpoint_repository_factory(session)
            checkpoint = repository.get(job_id)
            if checkpoint is None:
                checkpoint = MetadataIndexSyncCheckpoint(
                    job_id=job_id, last_arxiv_id=None, status="pending", records_indexed=0,
                    last_error=None, updated_at=datetime.now(timezone.utc),
                )
                return repository.create(checkpoint)
            return checkpoint

    def _save(self, checkpoint: MetadataIndexSyncCheckpoint) -> None:
        checkpoint.updated_at = datetime.now(timezone.utc)
        with self.database.get_session() as session:
            self.checkpoint_repository_factory(session).save(checkpoint)

    @staticmethod
    def _summary(checkpoint: MetadataIndexSyncCheckpoint, batches: int, attempted: int) -> dict[str, Any]:
        return {
            "job_id": checkpoint.job_id,
            "status": checkpoint.status,
            "last_arxiv_id": checkpoint.last_arxiv_id,
            "batches_processed": batches,
            "records_attempted": attempted,
            "records_indexed": checkpoint.records_indexed,
            "last_error": checkpoint.last_error,
        }


def main(argv: list[str] | None = None) -> int:
    import argparse
    import logging

    from src.config import get_settings
    from src.db.factory import make_database
    from src.services.opensearch.factory import make_opensearch_client_fresh

    parser = argparse.ArgumentParser(description="Sync a bounded batch of PostgreSQL metadata to OpenSearch")
    parser.add_argument("--job-id", required=True, help="Stable ID to resume; run one process per ID")
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--max-batches", type=int, default=5)
    args = parser.parse_args(argv)
    database = None
    try:
        settings = get_settings()
        database = make_database(settings)
        summary = MetadataIndexSyncService(database, make_opensearch_client_fresh(settings)).run(
            job_id=args.job_id, batch_size=args.batch_size, max_batches=args.max_batches
        )
        print(summary)
        return 0 if summary["status"] != "failed" else 1
    except Exception as exc:
        logging.getLogger(__name__).error("Metadata index sync failed (%s)", type(exc).__name__)
        return 1
    finally:
        if database is not None:
            database.teardown()


if __name__ == "__main__":
    import logging

    logging.basicConfig(level=logging.INFO)
    raise SystemExit(main())
