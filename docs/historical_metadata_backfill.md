# Historical metadata backfill (Phase 2B)

The backfill is a manual CLI operation. It does not run at API startup or from
the daily Airflow DAG, and it stores arXiv metadata in PostgreSQL only.

Example invocation (do not use against a live database without an explicit
operator decision):

```powershell
python -m src.services.historical_backfill `
  --job-id ai-ml-2017-2020-v1 `
  --start-date 20170101 `
  --end-date 20201231 `
  --categories cs.AI,cs.LG,stat.ML `
  --window-days 7 `
  --page-size 100 `
  --max-pages 5
```

The job ID identifies a durable checkpoint. Resume by invoking the same command
with the same job ID and the same date range, categories, window size, and page
size. `--max-pages` is only a per-invocation work budget and may be changed.
To start with different query parameters, explicitly use a new job ID. One
process should run a given job ID at a time.

Each execution is bounded to 1–100 pages; each page is at most 2,000 papers;
date windows are at most 365 days. Defaults are 5 pages, 100 papers per page,
and 7-day windows. Requests are sequential and use the existing ArxivClient
rate limiter. Failed API or database operations stop the execution; rerunning
the same job resumes from the last committed cursor. Page writes use the
existing exact-`arxiv_id` upsert, so a partially written page can safely be
replayed before its checkpoint advances.

## Checkpoint table creation

This repository has no Alembic migration framework. The new SQLAlchemy model is
registered before the existing `Base.metadata.create_all()` call in PostgreSQL
startup. On a future normal deployment startup, that existing mechanism will
create `historical_backfill_checkpoints` if it is absent. This implementation
does not connect to a database, run startup, execute `create_all`, or apply a
migration. Review the table creation behavior during deployment planning.

## Deliberate limits

- The date filter is arXiv `submittedDate`; it is not a guarantee of exhaustive
  historical coverage. API result ceilings, changing records, and pagination
  ordering may require a later coverage audit.
- Atom IDs retain their arXiv version suffix. Exact-version upsert is reused;
  canonical-paper/version-history handling is not part of this phase.
- This job does not download PDFs, call Docling, generate embeddings, or write
  to OpenSearch. PostgreSQL records created here therefore do **not** become
  searchable through the existing OpenSearch-backed endpoints automatically.
  Metadata discovery/indexing requires a separate reviewed change.
- The backfill records metadata and abstracts only. It does not create a
  persistent PDF-processing failure state or a historical coverage manifest
  beyond its per-job cursor and aggregate counts.
