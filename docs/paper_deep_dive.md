# On-demand Paper Preparation and Deep Dive

This workflow operates on one exact stored arXiv ID/version. It does not change the scheduled Airflow ingestion configuration and does not process papers in batches.

## API flow

1. `POST /api/v1/papers/{arxiv_id}/prepare` loads the exact ID from PostgreSQL. Existing parsed text and verified chunks are reused. Otherwise, the existing arXiv client downloads that exact ID (including its version suffix) to the local PDF cache. The request uses the configured download timeout/retries and enforces `PDF_PARSER__MAX_FILE_SIZE_MB` while streaming. The existing Docling parser then enforces configured file-size and page-count limits.
2. Extracted text, sections, references, parser metadata, and processing time are stored on the existing `Paper` row before indexing. The existing section-aware chunker, Jina embeddings client, and OpenSearch hybrid index are used for only that paper. The API verifies exact-paper chunks before returning `ready`.
3. If indexing fails after parsing was saved, the endpoint returns HTTP 503 with code `parsed_not_indexed` and `parsed_content_saved: true`. Retrying reuses the PostgreSQL full text and retries indexing without another download/parse. Incomplete chunks for that exact ID are removed before a retry index to avoid duplicate chunks.
4. `POST /api/v1/papers/{arxiv_id}/deep-dive` requires stored full text and indexed chunks. It makes at most one query embedding and one paper-scoped OpenSearch search per request; if embedding fails, it degrades only to paper-scoped BM25. Returned hits are filtered again by exact `arxiv_id` before prompt construction.

Preparation and generation are bounded synchronous HTTP requests, not queued jobs. Deployments should configure HTTP/proxy request timeouts to accommodate Docling. No distributed task queue is introduced.

## Deep Dive contract and persistence

The structured brief includes summary, problem, contributions, method, reported results, author-stated limitations, separate inferred caveats, implementation details, engineering takeaways explicitly labeled as reported fact or inference, validated evidence references, and information gaps. Missing scalar fields use `Unavailable from the retrieved paper evidence.` No page references are generated.

At most `DEEP_DIVE__MAX_CHUNKS` (default 10) are passed to the prompt. The prompt is capped by `DEEP_DIVE__MAX_PROMPT_CHARS` (default 24,000 characters), with each excerpt capped by `DEEP_DIVE__MAX_CHUNK_CHARS` (default 5,000). The evidence query asks for problem, methods, experiments, results, limitations, and implementation details in one retrieval pass.

Generated JSON is validated with Pydantic. Each cited chunk ID must exist in the selected context, any stated section must match indexed provenance, and the quoted excerpt must be contained in that context. Invalid references are removed and recorded as information gaps. The current chunk index does not retain reliable page numbers.

Successful briefs are stored in the new `paper_briefs` table. Compatibility is keyed by exact `arxiv_id`, model, prompt/schema version, actual retrieval mode, effective top-k, and a hash of retrieved chunk IDs/sections/excerpts. A changed evidence context therefore invalidates a previous result. Failed generation is never saved. PostgreSQL is used for durable brief reuse; Redis remains unchanged.

The table is registered with the project's existing SQLAlchemy `Base.metadata.create_all()` mechanism. This adds a new table only; it does not alter existing tables. No database startup or migration was run during implementation. A normal application startup can create the missing table where the existing startup mechanism is used.

## API states

- Preparation: `404` paper missing; `502` PDF download failed; `422` parsing failed; `503 parsed_not_indexed` means parsed text is persisted and can be indexed by retry; `200 ready` means exact-paper chunks were verified.
- Deep Dive: `404` missing paper; `409 paper_not_prepared`; `422 insufficient_evidence` when no relevant exact-paper chunks are found; `503` for search, generation, or persistence failures. A successful response has `cached: true` when a compatible persisted brief is reused.

The PDF cache is local to the application host and may not be shared across multiple API workers; correctness does not depend on that cache because parsed text is persisted in PostgreSQL. Concurrent preparation requests for the same ID are not serialized, so run one preparation per selected paper at a time. Versioned IDs remain distinct records; no canonical-version policy is introduced.
