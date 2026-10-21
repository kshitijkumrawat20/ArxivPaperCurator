# Paper metadata discovery (Phase 2C)

The application now maintains a paper-level BM25 index alongside (not instead of)
the existing chunk/vector index. Its name is
`{OPENSEARCH__INDEX_NAME}-{OPENSEARCH__METADATA_INDEX_SUFFIX}`; the suffix defaults
to `metadata`. The chunk index remains `{index_name}-{chunk_index_suffix}` and its
hybrid/RRF query behavior is unchanged.

The metadata mapping stores `arxiv_id`, title, abstract, authors, categories,
publication date, PDF URL, and PostgreSQL `updated_at`. There is no vector field.
The exact versioned arXiv ID is the deterministic OpenSearch document ID. Index
operations are upserts, so a retry is safe and changed PostgreSQL metadata replaces
the old indexed document. PostgreSQL remains authoritative.

## Discovery API

`GET /api/v1/papers/discover` uses BM25 across title, abstract, and authors.
Repeated `categories` query parameters are supported, as are `date_from` and
`date_to` (inclusive dates), `size` (1–100), and `offset`. Results are sorted by
publication date newest first. An empty `query` lists newest papers within the
filters. `source_url` is the same arXiv PDF link as `pdf_url`. OpenSearch failures
return HTTP 503. The route is registered before `/papers/{arxiv_id}`.

## Daily ingestion and recovery

After fetch/storage, the Airflow DAG runs metadata indexing and existing PDF/chunk
indexing as sibling tasks. The metadata task reads only the fetched arXiv IDs back
from PostgreSQL; it does not download a PDF, parse text, embed, or call an LLM.
Airflow retries are safe because IDs are deterministic. A failed metadata task is
visible in its Airflow task state/logs and does not prevent the sibling hybrid task
from running; retry the task or use the bounded PostgreSQL sync below to recover
rows missed by the online handoff.

## Bounded manual PostgreSQL-to-index sync

Run a small batch, inspect its printed counts/status, and resume with the same job
ID. One process per job ID is supported. The independent table
`metadata_index_sync_checkpoints` stores a lexicographic arXiv-ID cursor; it does
not reuse the Phase 2B date-window checkpoint semantics.

Example only (not run during implementation):

```powershell
python -m src.services.metadata_index_sync --job-id metadata-sync-2020-v1 --batch-size 100 --max-batches 2
```

`batch-size` is limited to 500 and `max-batches` to 100 per invocation. A paused
job can be continued with the same ID and a different per-run batch budget. The
service reads existing PostgreSQL rows in keyset batches and never contacts arXiv.
If any document in a bulk request fails, the cursor is not advanced for that batch;
already successful documents are overwritten idempotently on retry. A failed job
prints failure counts/error and can be resumed manually. New rows whose arXiv ID
sorts before an already passed cursor are not included in that job; start a new job
to cover them. No automatic full historical sync runs at application startup.

The new checkpoint model is registered with the repository's existing SQLAlchemy
`create_all()` mechanism, as Phase 2B did. There is no Alembic migration in this
repository; a normal application/database startup may create the checkpoint table
if absent. No startup, migration, or live table operation was executed as part of
Phase 2C.

## Version and coverage notes

Version suffixes remain separate IDs/documents exactly as PostgreSQL stores them;
this phase does not choose a canonical version or merge versions. `updated_at`
records the latest metadata update timestamp available in PostgreSQL, not a
separate arXiv version history. A historical sync is bounded and manually resumed,
not an exhaustive coverage guarantee. It indexes only rows already stored in
PostgreSQL.
