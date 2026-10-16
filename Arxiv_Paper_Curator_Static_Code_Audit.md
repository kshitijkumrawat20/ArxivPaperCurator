# Arxiv Paper Curator — Static Code Audit

**Audit date:** 2026-10-16  
**Scope:** source in this workspace at commit `cc42c3a` plus the untracked checklists supplied with the audit request.  
**Method:** static inspection only. No application, containers, tests, external services, remote server, ingestion, or database were run or changed. The running deployment may differ from this source snapshot.

## Status legend

- **IMPLEMENTED** — an end-to-end source path is visible for the stated technical capability.
- **PARTIAL** — a reusable building block exists, but it does not meet the product requirement or has a material wiring/correctness gap.
- **MISSING** — no source implementation was found.
- **UNVERIFIED** — source alone cannot establish the claim.
- **NOT APPLICABLE** — not needed for the lean MVP at this stage.

## A. Executive inventory

The repository contains a substantive *single shared-corpus research backend*: FastAPI, PostgreSQL paper storage, an arXiv Atom client, cached PDF download, Docling parsing, section-aware chunking, Jina embeddings, OpenSearch BM25/vector/hybrid search, traditional and agentic RAG, Redis answer caching, Langfuse tracing, an Airflow DAG, and optional Telegram/Gradio interfaces.

It does **not** yet contain the product layer for the proposed MVP: no authenticated users, topic preferences, saved searches, projects, recommendations, briefs, collections, notifications/digests, usage tracking, or billing.

Two source-level defects materially change the initial inventory:

1. `HybridIndexingService.index_paper()` returns inside its chunk loop, so only the first accumulated chunk is passed to `bulk_index_chunks`; the declared count still says all chunks were created. This makes full-paper retrieval **PARTIAL**, not reliably implemented. Evidence: `src/services/indexing/hybrid_indexer.py:92-131`; invoked by `airflow/dags/arxiv_ingestion/indexing.py:12-35`.
2. Metadata-only ingestion is supported by `MetadataFetcher`, but the scheduled DAG requests `process_pdfs=True`; moreover `TextChunker.chunk_paper()` returns no chunks for a paper with neither sections nor full text. Metadata-only papers therefore are stored but are not searchable through the chunk index. Evidence: `src/services/metadata_fetcher.py:43-129`, `airflow/dags/arxiv_ingestion/fetching.py:27-34,60-64`, `src/services/indexing/text_chunker.py:54-91`.

The registered API surface is `/api/v1/health`, `/api/v1/ask`, `/api/v1/stream`, `/api/v1/search/`, `/api/v1/ask-agentic`, and `/api/v1/feedback`. `src/routers/paper.py` defines list/detail handlers but is not included by `src/main.py`; README paper endpoints are consequently a source/documentation mismatch.

## B. Completed feature inventory

### B1. Ingestion, storage, and historical corpus

| Capability | Status | Evidence | Present / gap / reuse |
|---|---|---|---|
| arXiv Atom/XML metadata client | IMPLEMENTED | `src/services/arxiv/client.py:51-135,184-309`; `ArxivPaper` | Fetches the configured category, parses ID/title/authors/abstract/categories/published date/PDF URL. Reuse the client and schema. |
| Configurable AI/ML category set | PARTIAL | `src/config.py:25-49`; `ArxivClient.fetch_paperts()` | One `search_category` string defaults to `cs.AI`; no category collection, per-job category iteration, or user-topic mapping. |
| Date-range query | PARTIAL | `ArxivClient.fetch_paperts(... from_date, to_date ...)` | Builds an arXiv `submittedDate` range. It is only a primitive: the caller cannot select categories and no public discovery API exposes a date filter. |
| Offset pagination primitive | IMPLEMENTED | `src/services/arxiv/client.py:51-101` | `start` is accepted and results capped to 2,000. No caller advances it automatically. |
| Bounded, resumable historical backfill | MISSING | searched `src/`, `airflow/` | No checkpoint table/file, range planner, cursor persistence, or restart workflow. Reuse the date and start primitives plus `PaperRepository.upsert()`. |
| Incremental daily fetch | PARTIAL | `airflow/dags/arxiv_paper_ingestion.py:25-79`; `fetching.py:37-74` | Weekday DAG fetches only the day before, max results defaults to 5, `catchup=False`; weekends/missed days and daily completeness are not recovered. |
| Metadata-only ingestion | PARTIAL | `MetadataFetcher.fetch_and_process_papers(process_pdfs=False)` | Callable service path exists, but DAG uses `True` and metadata-only papers do not create indexable chunks. This is a high-value reuse point after adding metadata/abstract indexing. |
| PDF caching, retry, and parser | PARTIAL | `src/services/arxiv/client.py:337-435`; `src/services/metadata_fetcher.py:131-316`; `src/services/pdf_parser/docling.py` | Local cache, retry loops, download/parse semaphores, and Docling service exist. No host allow-list, response content-type/size validation before writing, persistent failure state, or on-demand API workflow. |
| Parsed text, sections, references, parser metadata | IMPLEMENTED | `src/models/paper.py:25-35`; `MetadataFetcher._serialize_parsed_content()` | Stored on `Paper`; sections and references can seed deep-dive evidence. Page-level provenance is not represented in the model/index. |
| PostgreSQL metadata upsert | PARTIAL | `Paper.arxiv_id` unique; `PaperRepository.upsert()` | Same exact `arxiv_id` updates metadata, but Atom IDs retain `vN`. A new arXiv version becomes a separate paper instead of a canonical-paper update/history. Per-item commits also prevent an atomic batch. |
| Version/update policy | MISSING | `src/models/paper.py`; `ArxivClient._get_arxiv_id()` | No canonical ID, version field, `updated` Atom date, or version-history model. `fetch_paper_by_id()` strips a version but list ingestion does not normalize it. |
| Duplicate-free OpenSearch reindex | PARTIAL | `delete_paper_chunks()`, `reindex_paper()`; DAG uses `replace_existing=True` | Explicit deletion exists, but chunk documents have no deterministic `_id`, direct indexing duplicates, and the live DAG path hits the first-chunk return defect. |
| Airflow reusable orchestration | PARTIAL | `airflow/dags/arxiv_paper_ingestion.py`; `fetching.py`; `indexing.py` | Main DAG calls the reusable fetcher and hybrid indexer with retries. Its selection uses most recently `created_at` records rather than an exact run manifest and has no recovery/checkpoint semantics. |

### B2. Search, retrieval, RAG, and caching

| Capability | Status | Evidence | Present / gap / reuse |
|---|---|---|---|
| Section-aware chunking | PARTIAL | `src/services/indexing/text_chunker.py` | Section fallback/overlap logic is present. `chunk_text()` calls `_reconstruct_text(words, text)` with two arguments at line 114 although the helper accepts one, breaking the short-text path; offsets are approximate and no page provenance survives. |
| Jina passage/query embeddings | IMPLEMENTED | `src/services/embeddings/jina_client.py:10-104` | Uses Jina v3 at 1,024 dimensions with batches and a 30-second client timeout. No retry/rate-limit/cost metering. |
| BM25 search | IMPLEMENTED | `QueryBuilder`; `OpenSearchClient._search_bm25_only()`; `/search/` | Chunk search, highlights, category filter, score, and offset pagination are wired. Reuse for project candidate generation. |
| Hybrid RRF search | PARTIAL | `index_config_hybrid.py`; `OpenSearchClient._search_hybrid_native()` | Native hybrid/RRF pipeline is defined. `from_` is ignored on the hybrid route, and category filters are embedded only in the BM25 branch—not the kNN branch—so category-filtered hybrid results need correction before relying on them. |
| Search pagination and historical filters | PARTIAL | `HybridSearchRequest`; `QueryBuilder` | `size`/`from` limits exist for BM25; no search date-range filter and hybrid ignores `from`. Historical discovery only searches what has been indexed. |
| Paper-scoped retrieval primitive | PARTIAL | `OpenSearchClient.get_chunks_by_paper(arxiv_id)` | Internal fetch-all-chunks helper exists, limited to 1,000. It is not used by RAG or exposed through request schemas. Query builder/search methods have no `arxiv_id` filter. |
| Traditional RAG | IMPLEMENTED | `src/routers/ask.py:19-167`; `AskRequest`; `OllamaClient` | Retrieves chunks then prompts Ollama; empty retrieval is handled and URLs are returned. Reuse retrieval and answer generation, but return chunk/section references rather than only paper URLs. |
| Streaming RAG | PARTIAL | `src/routers/ask.py:170-273` | Emits SSE-shaped `data:` events and caches answers. Media type is `text/plain`, completion/error contracts differ, there is no disconnect cancellation, and generation timeout is not enforced by the router. |
| Agentic RAG | PARTIAL | `src/services/agents/`; `/api/v1/ask-agentic` | Guardrail → retrieve → grade → rewrite → generate graph is wired with bounded attempts. The router passes only query/model, silently ignoring `top_k`, `use_hybrid`, and `categories` in `AskRequest`; retrieval is global, not paper- or user-scoped. |
| Source-grounded citations | PARTIAL | `ask.py:57-76`; agent `tools.py:61-75` | Traditional RAG returns deduplicated arXiv PDF URLs; agent sources include document metadata. Neither response contract maps each claim to a chunk, section, page, or quoted supporting passage. |
| Structured research briefs | MISSING | searched routers/schemas/services/models | There is Q&A prompt generation only; no brief schema, extraction service, cache/status record, or evidence-per-field policy. Reuse paper data, parser output, scoped retrieval primitive, Ollama client, Redis patterns. |
| Exact request-answer cache | PARTIAL | `src/services/cache/client.py` | Key includes query/model/top-k/hybrid/categories and TTL. It omits corpus/index version and prompt version; no paper scope yet. Shared cache is unsafe once private contexts/users are added. |
| Langfuse tracing and answer feedback | PARTIAL | `src/services/langfuse/`; `agentic_ask.py` | Tracing paths exist. `FeedbackRequest` defines `comments`, while router reads `request.comment`; the endpoint will raise at runtime. No user identity/ownership or durable product feedback store exists. |

### B3. Interfaces, application wiring, and SaaS foundations

| Capability | Status | Evidence | Present / gap / reuse |
|---|---|---|---|
| FastAPI app/lifecycle/dependency injection | IMPLEMENTED | `src/main.py`; `src/dependencies.py` | Creates database/search/services at lifespan and injects them. Reuse this boundary for new routers/services. |
| Paper list/detail API | PARTIAL | `src/routers/paper.py`; absent from `src/main.py:112-116` | Schema/repository handlers exist but are not registered. README claims them. This is a wiring gap, not an implemented public API. |
| Health endpoint | PARTIAL | `src/routers/ping.py:17-78` | Checks database, OpenSearch, and Ollama and reports degraded status. It returns a normal success response when degraded and lacks separate liveness/readiness semantics. |
| Authentication/user identity | MISSING | searched models, schemas, routers, dependencies | `api_user` is a fixed tracing label, not identity. |
| User topics/saved searches/watchlists/collections | MISSING | searched source tree | No models/routes/ownership checks. |
| Projects/project-to-paper matches | MISSING | searched source tree | No project profile, ranker, explanation, feedback, or persistence. Reuse BM25/embedding search for candidates. |
| Digests/alerts | MISSING | Airflow only ingests; `TelegramBot` only answers questions | No user subscription, scheduler job, delivery record, email sender, or notification preference. |
| Saved briefs | MISSING | searched models and cache | Redis stores transient whole answers only; no brief model/status/version/cache. |
| Usage quotas/metering/billing | MISSING | searched source tree | No per-user counter, rate limiter, Stripe/payment integration, or subscription state. |
| Multi-user data isolation | MISSING | only shared `papers` model | No private data currently exists, but all new user data needs owner filters at repository and retrieval layers. |
| API security/production controls | PARTIAL | `src/config.py`; `compose.yml`; `src/middleware.py` | Configuration is centralized, but no auth, CORS middleware, API request throttling, or production security config is wired. Local compose disables OpenSearch security, so it must not be exposed as-is. |
| Telegram and Gradio | PARTIAL | `src/services/telegram/`; `src/gradio_app.py` | Optional demo integrations reuse parts of RAG. Telegram is not a personalized-digest system and neither is a multi-user product UI. |

## C. Proposed MVP gap matrix

| Feature | Reuse now | Missing work and endpoint/data changes | Integration points | Priority / complexity |
|---|---|---|---|---|
| Corpus reliability (prerequisite) | `ArxivClient`, `MetadataFetcher`, `PaperRepository`, Airflow DAG, `HybridIndexingService` | Fix full chunk indexing and short-text chunk path; canonical ID/version policy; metadata/abstract index records; category iteration; backfill cursor and run manifest; date/range API filters | PostgreSQL paper/run tables, Airflow, OpenSearch mapping and deterministic IDs | **P0 / High** |
| Paper-scoped retrieval (prerequisite) | `get_chunks_by_paper`, chunk `arxiv_id`, `AskRequest`, `QueryBuilder` | Add `arxiv_id` filter through API schema → all BM25/kNN/hybrid clauses → RAG/agent context; reject/handle unindexed papers | FastAPI search/ask, OpenSearch, PDF/on-demand processing | **P0 / Medium** |
| Paper Deep Dive | parser output, chunks, RAG/Ollama, cache factory | `PaperBrief` persistent model with status/version; brief request/response schema; on-demand download/parse/index orchestration; validated structured output; claim evidence object (paper/version/section/chunk/page when available); retry and abstract-only state | PostgreSQL, OpenSearch scoped retrieval, Redis or DB cache, Ollama, API | **P1 / High** |
| Personalized Paper Radar | paper metadata, BM25/hybrid candidate search, Airflow schedule, Telegram optional channel | Minimal auth/pilot identity; topic/saved-search model; category/keyword/time window; feed/recommendation and saved/dismissed model; rank reason; digest-run/delivery table and one notification channel | PostgreSQL ownership, daily metadata intake, OpenSearch, scheduler, email *or* Telegram | **P1 / High** |
| Project-to-Paper Match | search API, Jina query embeddings, paper metadata/abstract | Project profile model; match request endpoint; candidate retrieval with metadata/category first; cross-paper dedupe/ranking; evidence-grounded relevance explanation; feedback flags and optional saved match | PostgreSQL, OpenSearch, existing embedding and generation clients | **P1 / Medium** |
| Public-pilot safeguards | settings/dependencies, cache, Langfuse traces | Auth, owner authorization, simple request/generation quotas, rate limiting, CORS/TLS/secret review, product retention/deletion policy | FastAPI middleware/dependencies, PostgreSQL usage records, deployment | **P2 / Medium** |
| Monetization | none | Subscription state, payment flow, webhook idempotency, cancellations, quota resets | Auth/usage first; payment provider later | **P3 / Medium** |

## D. Architecture integration map

```text
arXiv API
  -> ArxivClient -> metadata-only Paper upsert (canonical ID + version policy)
  -> on selected paper/deep dive: PDF cache -> Docling -> Paper parsed fields
  -> HybridIndexingService -> OpenSearch chunks + metadata/abstract discovery record

FastAPI
  -> identity/owner dependency
  -> topics/projects/briefs/collections repositories in PostgreSQL
  -> search candidates in OpenSearch (owner filters for private data; arxiv_id for deep dive)
  -> existing Jina + Ollama services for rerank/explanation/brief generation
  -> Redis cache keyed by corpus/paper version + model + prompt/schema + owner where applicable

Airflow (or one inexpensive scheduler)
  -> bounded daily incremental metadata ingest
  -> resumable historical backfill
  -> per-topic digest generation/delivery after corpus run succeeds
```

Keep the current shared paper corpus. Do not add another vector database: OpenSearch already has the needed chunk metadata, kNN mapping, and RRF path. For the budget, metadata/abstract discovery should happen first; PDF parsing and full-text embedding should be triggered only for selected papers/deep dives or a tightly bounded high-relevance queue.

## E. Recommended implementation sequence

1. **Source parity and retrieval correctness.** Record the deployed commit separately; repair/review the indexing loop, short-text path, paper-router registration, feedback field mismatch, and hybrid filter/pagination behavior. Add focused unit tests before changing product scope.
2. **Corpus contract.** Define canonical paper/version/update fields and an OpenSearch document-ID policy. Add metadata/abstract discovery indexing and the bounded, resumable metadata backfill design. Keep PDF processing optional.
3. **Paper-scoped retrieval.** Thread `arxiv_id` from Pydantic request to both hybrid query branches and both RAG workflows. Return stable paper/chunk/section references.
4. **Paper Deep Dive.** Add an on-demand processing state machine and persistent, versioned brief record. Start with one validated brief schema and explicit `not found`/`abstract-only` states.
5. **Pilot identity plus Paper Radar.** Add the smallest secure authentication approach and user-owned topics, feed, saved/dismissed signals, then one digest delivery channel. Enforce ownership in every read/write path.
6. **Project-to-Paper Match.** Add project profiles, reuse metadata-first candidate retrieval, then generate short evidence-based explanations and collect relevance feedback.
7. **Operate a small pilot.** Add quotas/cost records and public API hardening only when private user data or outside users are enabled. Delay billing until repeated usage and willingness to pay are demonstrated.

Each package is independently reviewable and should preserve the current RAG code except where the required filter or source-reference contract must change.

## F. Questions and uncertainties

- Is remote deployment on `cc42c3a`, and does it include local/uncommitted fixes? Static source cannot establish this.
- What data already exists in PostgreSQL/OpenSearch, including whether previously indexed documents bypassed the current first-chunk indexing bug?
- Does the remote environment use a non-default `ARXIV__MAX_RESULTS` or `ARXIV__SEARCH_CATEGORY`? Values in `.env` were intentionally not inspected or reproduced.
- Has arXiv API behavior for the submitted-date query, multi-category coverage, and updated versions been runtime-validated at the desired historical scale? Source cannot prove it.
- Does Docling output page/source coordinates in its runtime metadata that could be preserved for citation evidence? The database/index schema does not expose page provenance.
- What pilot identity and delivery channel are desired? This materially affects the minimum auth and notification work.
- What retention/privacy commitments apply to project descriptions and generated briefs? A design decision is required before storing them for multiple users.

## Five most important verified gaps and reusable code

1. **Chunk indexing is not reliable:** only the first chunk is bulk-indexed due to the return placement. Reuse `HybridIndexingService`, `TextChunker`, Jina, and OpenSearch rather than replacing them.
2. **Historical/incremental corpus is not production-complete:** there is a date and offset primitive, but no resumable backfill, complete category strategy, or missed-day recovery. Reuse `ArxivClient`, upsert, and Airflow.
3. **No genuine paper-specific RAG or deep dive:** an internal `get_chunks_by_paper()` helper exists, but no API/RAG filter or structured brief path. Reuse chunk metadata, parser output, traditional RAG, and caching.
4. **The proposed personalized and project-aware workflows are absent:** there is no user, topic, project, match, collection, or digest data model. Reuse metadata/BM25/hybrid retrieval as the candidate engine.
5. **The current API is not ready for multi-user public exposure:** it lacks authentication, isolation, quotas, and API protections; paper routes are unregistered and feedback contains a field mismatch. Reuse FastAPI dependency wiring and the existing shared corpus, then add only the minimum pilot safeguards.
