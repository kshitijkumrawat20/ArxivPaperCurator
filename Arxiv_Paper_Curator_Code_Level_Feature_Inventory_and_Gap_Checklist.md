# Arxiv Paper Curator — Code-Level Feature Inventory & MVP Gap Checklist

**Purpose:** Record what is already present in the repository, what is only partially supported, and what must be added for the lean AI/ML Research Intelligence MVP. This is a source-code review, not a runtime/test audit.

**Repository reviewed:** `kshitijkumrawat20/ArxivPaperCurator`, public `main` branch.  
**Review mode:** Static inspection of source files, route registration, schemas, models, configuration, and orchestration. No service was started and no tests were run as part of this review. The owner reports that the existing system has already been tested on a remote server; this document does not dispute or repeat those runtime tests.

## Status legend

- **PRESENT IN SOURCE** — implementation is visible in the inspected source files.
- **PARTIAL** — the building block exists, but it does not yet cover the product use case end-to-end.
- **WIRING GAP** — code exists but is not registered/connected in the main application path seen in the repository.
- **MISSING** — no corresponding model, route, or implementation was found in the inspected repository tree.
- **LATER** — intentionally outside the first low-cost MVP.

---

# 1. Existing Backend Inventory

## 1.1 Ingestion and data storage

| Capability | Status | Code evidence / notes |
|---|---|---|
| arXiv API client and Atom/XML parsing | PRESENT IN SOURCE | `src/services/arxiv/client.py` |
| Configurable arXiv category | PARTIAL | `src/config.py` defines `ARXIV__SEARCH_CATEGORY`; default is `cs.AI`, singular category configuration. |
| Date-range search | PRESENT IN SOURCE | `ArxivClient.fetch_paperts()` accepts `from_date` and `to_date` and builds a `submittedDate` query. |
| Offset pagination primitive | PRESENT IN SOURCE | `fetch_paperts()` accepts `start`; one call fetches up to a capped 2,000 results. |
| Automatic multi-page historical backfill/resume | MISSING | No dedicated resumable backfill job/cursor was found in the source tree. Passing `start` manually is not a full backfill workflow. |
| API request delay/rate-limit handling | PARTIAL | `rate_limit_delay` exists and the normal `fetch_paperts()` path uses an in-client delay. Confirm coverage across all methods/workers before relying on it as a global limiter. |
| PDF download/cache/retry path | PRESENT IN SOURCE | `src/services/arxiv/client.py`; PDF cache path is configurable. |
| Scientific PDF parsing with Docling | PRESENT IN SOURCE | `src/services/pdf_parser/docling.py` and PDF parser service abstractions. |
| Extracted raw text, sections, references and parser metadata | PRESENT IN SOURCE | `src/models/paper.py`, `src/schema/arxiv/paper.py`, `src/services/metadata_fetcher.py`. |
| PostgreSQL paper metadata storage and upsert | PRESENT IN SOURCE | `src/models/paper.py`, `src/respositories/paper.py`, `src/services/metadata_fetcher.py`. |
| Section-aware chunking | PRESENT IN SOURCE | `src/services/indexing/text_chunker.py`; configuration defaults are 600-word chunks, 100-word overlap, and section-aware chunking. |
| Chunk embeddings and OpenSearch indexing | PRESENT IN SOURCE | `src/services/indexing/hybrid_indexer.py`, embedding client and OpenSearch client modules. |
| Daily ingestion orchestration | PRESENT, BUT LIMITED | `airflow/dags/arxiv_paper_ingestion.py` schedules Monday–Friday at 06:00 UTC. `airflow/dags/arxiv_ingestion/fetching.py` targets the previous day and uses configured `max_results`; the default in `src/config.py` is 5. |
| Reliable daily completeness for all target AI/ML categories | PARTIAL | Current configuration defaults to one category and five results per fetch. The code should not be assumed to ingest every new AI/ML paper each day. Weekend/backfill coverage also needs an explicit design. |
| Historical metadata corpus for 8–9 years | PARTIAL | Date-filtering and offset primitives exist, but a historical backfill workflow with paging, checkpointing, deduplication, retry/resume, and metadata-first mode is not visible. |
| Stable paper version history | MISSING / UNVERIFIED | There is a unique `arxiv_id` field, but no explicit paper-version history model/workflow was found in the inspected tree. Verify ID normalization and version-update behavior before building history features. |

## 1.2 Search, retrieval and RAG

| Capability | Status | Code evidence / notes |
|---|---|---|
| BM25/lexical search | PRESENT IN SOURCE | `src/services/opensearch/query_builder.py`, `src/services/opensearch/client.py`. |
| Vector search using Jina embeddings | PRESENT IN SOURCE | `src/services/embeddings/jina_client.py`, embedding schemas/factory. |
| Hybrid search and Reciprocal Rank Fusion configuration | PRESENT IN SOURCE | `src/services/opensearch/index_config_hybrid.py`, query/client and indexing modules. |
| Search pagination/category filter/latest-first option | PRESENT IN SOURCE | `src/schema/api/search.py`, `src/routers/hybrid_search.py`, `src/services/opensearch/query_builder.py`. |
| Traditional RAG endpoint | PRESENT IN SOURCE | `src/routers/ask.py`; included in `src/main.py` under `/api/v1`. |
| Streaming answer endpoint | PRESENT IN SOURCE | `stream_router` in `src/routers/ask.py`; registered in `src/main.py`. |
| Agentic RAG workflow | PRESENT IN SOURCE | `src/services/agents/agentic_rag.py` and nodes under `src/services/agents/nodes/`. Includes guardrail routing, retrieval, document grading, query rewrite and answer generation. |
| Source paper URLs in answers | PRESENT IN SOURCE | `src/routers/ask.py` prepares arXiv PDF URLs from retrieved chunk IDs; agentic response exposes `sources`. |
| Langfuse tracing/observability | PRESENT IN SOURCE | `src/services/langfuse/` and tracing integration in RAG/agent nodes. |
| RAG feedback endpoint | PRESENT IN SOURCE | `POST /api/v1/feedback` in `src/routers/agentic_ask.py`; feedback is sent to Langfuse. |
| Exact-match query response cache | PRESENT IN SOURCE | `src/services/cache/` and traditional RAG integration in `src/routers/ask.py`. |
| Paper-scoped retrieval (`paper_id`/`arxiv_id` filter) | MISSING AS A PRODUCT API | Current ask schema exposes `query`, `top_k`, `use_hybrid`, `model`, and `categories`; no paper identifier filter is defined there. Search query builder supports categories but not a paper-level scope in its public request schema. |
| Structured research brief extraction | MISSING | Existing RAG returns Q&A-style answers. No dedicated structured output/service was found for method, assumptions, benchmark setup, results, limitations, reproducibility, code availability and evidence per claim. |
| Paper-to-paper comparison workflow | MISSING | No comparison endpoint/schema/service found. |
| Project-aware paper relevance | MISSING | No project profile schema, endpoints, saved stack/problem context, or project-to-paper scoring workflow found. |
| Personalized topic feed/ranking | MISSING | No user watchlist/topic preference model or per-user recommendation pipeline found. |

## 1.3 Existing API and interfaces

| Capability | Status | Code evidence / notes |
|---|---|---|
| FastAPI application and API docs | PRESENT IN SOURCE | `src/main.py`. |
| Health/ping endpoints | PRESENT IN SOURCE | `src/routers/ping.py`, registered in `src/main.py`. |
| Hybrid search endpoints | PRESENT IN SOURCE | `src/routers/hybrid_search.py`, registered in `src/main.py`. |
| Telegram bot | PRESENT IN SOURCE | `src/services/telegram/`; optional startup integration in `src/main.py`. This is not yet a per-user SaaS notification system. |
| Gradio test/demo interface | PRESENT IN SOURCE | `src/gradio_app.py`, `gradio_launcher.py`. This is not a customer-facing multi-user web application. |
| Paper list/detail route module | WIRING GAP | `src/routers/paper.py` defines `GET /papers/` and `GET /papers/{arxiv_id}`, but `src/main.py` does not include `paper.router` in the FastAPI app. `src/routers/__init__.py` imports the module, but that alone does not register its routes. Verify the deployed entrypoint matches repository `main`; if it does, register the router. |
| User-facing web frontend | MISSING | No dedicated frontend application/source tree was found in the repository. |
| Email digest delivery | MISSING | No per-user email preference/delivery workflow found. |
| Saved papers / collections / reading lists | MISSING | No collection/bookmark model and routes found. |
| Markdown/BibTeX export | MISSING | No export workflow found in API source. |

## 1.4 SaaS/product foundations

| Capability | Status | Notes |
|---|---|---|
| User registration/login/session | MISSING | No user model/auth router was found. |
| User profile and selected topics | MISSING | No user preference schema/API found. |
| Projects/workspaces | MISSING | No project or workspace model/routes found. |
| Usage metering and per-user quotas | MISSING | Existing arXiv request-delay logic is not SaaS usage metering. No per-user AI-call/token/brief quotas found. |
| Billing/subscription/payment webhooks | MISSING | No subscription/billing model or payment route found. |
| Multi-tenant data isolation | MISSING | Current paper schema has no user/tenant ownership because papers are a shared corpus; private per-user data/workspaces are not implemented. |
| Public API security/rate limits | NEEDS PRODUCT DESIGN | No user authentication is apparent in the registered request flow. Do not expose a paid multi-user API without auth, request throttling, quotas and secret/config review. |
| License file | MISSING IN REPOSITORY TREE | Root listing has no `LICENSE` file. Choose a license deliberately before accepting outside contributions or distributing the code. |

---

# 2. Important Code-Level Findings

## Finding A — Existing work should be reused, not rebuilt

The repository already contains substantial ingestion, PDF parsing, chunking, hybrid retrieval, RAG, agentic RAG, caching, observability and orchestration. These should be retained as the technical core. The immediate work is mainly the product/data workflow around them, plus a few retrieval and ingestion gaps.

## Finding B — The Paper API route looks present but is not registered in the current app entrypoint

`src/routers/paper.py` contains list/detail route definitions, but `src/main.py` currently registers ping, ask, stream, hybrid search and agentic ask only. Treat this as a likely wiring gap based on the inspected `main` branch; reconcile it with the live remote deployment before changing it.

## Finding C — Current daily ingestion is not full AI/ML coverage

The configured arXiv category defaults to `cs.AI`, `max_results` defaults to 5, and the DAG runs Monday–Friday. That is enough for a working pipeline demonstration, but not sufficient to promise users a complete daily feed of all relevant AI/ML papers. The product should support a controlled set of categories/topics and prove ingestion completeness before marketing “all important papers.”

## Finding D — Historical access is partly supported, historical backfill is not yet a complete workflow

Date filters and a `start` offset exist in the arXiv client, and parsed content can be persisted. However, no resumable historical backfill job with pagination/checkpoints and a metadata-first approach was found. Add that rather than downloading and parsing every PDF immediately.

## Finding E — Existing RAG is not yet a Paper Deep Dive or Research Compiler

The existing RAG can answer questions over indexed chunks. The request contract does not expose a paper-scoped filter, and no dedicated structured extraction service was found for a per-paper method/benchmark/results/limitations/code brief. These are product features to add on top of existing retrieval, not reasons to replace the RAG core.

## Finding F — No customer identity, personalization or billing layer exists in source

There are no user, topic-subscription, project, collection, usage, or subscription models/routes in the inspected source tree. Build the smallest version necessary for a pilot; do not add enterprise multi-tenancy or payment automation before the core workflow is validated.

---

# 3. Recommended MVP Implementation Checklist (Prioritized)

## P0 — Close the source/data/API gaps first

- [ ] **Confirm deployed source parity:** compare the remote server's deployed commit/branch to GitHub `main`. Do not assume the remote app is identical to this snapshot.
- [ ] **Paper route wiring:** verify whether `src/routers/paper.py` is registered in the actual deployed entrypoint. If not, register it and confirm list/detail endpoints return the expected paper metadata/content.
- [ ] **Ingestion completeness decision:** define the initial category set (e.g., `cs.AI`, `cs.LG`, `cs.CL`, `cs.CV`, `stat.ML` as appropriate to target users) and implement category-aware fetching rather than assuming one category covers all AI/ML.
- [ ] **Daily incremental ingestion:** keep metadata-first ingestion by default; define recent-submission range, pagination, deduplication, retries, and how missed dates/weekends are recovered.
- [ ] **Historical metadata backfill:** implement a resumable, paginated metadata-only job for the chosen date window. Save a checkpoint/cursor and support restart without downloading all PDFs.
- [ ] **Paper-scoped retrieval:** add an explicit `arxiv_id`/paper ID filter through request schema → query builder/OpenSearch query → RAG service. Do not simulate scope by simply adding the paper title to the prompt.
- [ ] **Version and update policy:** define how arXiv versions are normalized, when metadata is refreshed, when existing chunks are re-indexed, and whether version changes are tracked or overwrite the current paper record.

**P0 completion evidence:** code paths and schemas are identifiable; endpoint wiring is clear; historical/daily jobs are resumable by design; the scoped retrieval filter reaches the actual OpenSearch query.

## P1 — Core product features that may be worth paying for

### A. Personalized Paper Radar

- [ ] Add a minimal user identity/profile for a private pilot (use a proven auth provider or small secure implementation; do not invent custom password storage casually).
- [ ] Add a topic/watchlist model with topic text, relevant categories/keywords, created/updated timestamps and user ownership.
- [ ] Generate a ranked paper feed using metadata/abstract first; store relevance reason and paper ID.
- [ ] Support saved/dismissed papers or at least feedback signals to improve ranking.
- [ ] Add scheduled digest generation (start with a single channel such as email OR Telegram; do not build all channels at once).

### B. Paper Deep Dive / Paper Compiler

- [ ] Add an endpoint for a selected paper's structured brief.
- [ ] Use the paper-scoped retrieval path for follow-up Q&A.
- [ ] Define a validated response schema for: problem, method, assumptions, benchmark/dataset, reported metrics, limitations, code/repository links, reproducibility notes and unanswered questions.
- [ ] Attach evidence to each extracted claim: paper ID plus section/page/snippet where available.
- [ ] Distinguish explicitly between author-reported facts, the model's inference, and information not found in the paper.
- [ ] Generate/cache the brief on demand; avoid processing all historical PDFs in advance.
- [ ] Make the workflow robust when the PDF is unavailable, parsing fails, a table cannot be extracted, or the paper does not report a metric.

### C. Project-to-Paper Match

- [ ] Add a minimal project profile (problem statement, stack, constraints, topic preferences). Keep it private to its owner.
- [ ] Start with lexical/category filtering and existing embeddings; do not add a separate vector database initially.
- [ ] Rank a small candidate set and generate a concise “why this is relevant” explanation grounded in metadata/abstract or full-text evidence.
- [ ] Include an uncertainty label and allow user feedback (“relevant”, “not relevant”, “already know this”).
- [ ] Provide a project brief that recommends papers to read, not claims that the approach will definitely improve the user's system.

## P2 — Minimum SaaS safety and monetization, only after a pilot proves repeat usage

- [ ] User authentication and ownership checks for projects, topics, collections, generated briefs and feedback.
- [ ] Request and generation quotas, rate limiting, timeouts, bounded retries and abuse protection.
- [ ] Per-user usage/cost records for embeddings and LLM calls; enforce a low default limit.
- [ ] Terms/privacy notice and content-retention/deletion policy appropriate for the deployed MVP.
- [ ] Basic subscription status and payment flow only after real users express willingness to pay.
- [ ] Billing webhook idempotency, failed-payment handling, cancellation and usage reset rules before charging customers.
- [ ] Production secrets, CORS, TLS, database access and logs reviewed before making the service public.

## P3 — Defer until demand is proven

- [ ] Automatic code execution/reproduction of papers.
- [ ] Autonomous agents that change a customer's code or run experiments.
- [ ] Full citation graph / all-scholarly-source ingestion.
- [ ] Team workspaces, SSO, enterprise audit logs and self-hosting product.
- [ ] Full-text backfill and embedding of every paper from every year.
- [ ] Multi-channel notifications and advanced research trend dashboards.

---

# 4. Resource and Cost Constraints

- [ ] Do not require a dedicated GPU.
- [ ] Do not require every existing Docker service to run in production at all times.
- [ ] Keep OpenSearch/Ollama available as the full local/portfolio stack, but deploy only the minimum services needed for the initial web workflow.
- [ ] Prefer metadata/abstract search for candidate discovery; download and parse full text only for selected/high-relevance papers or when the user opens a deep dive.
- [ ] Cache generated briefs and paper-specific answers with cache keys that include paper ID/version, model/prompt version and relevant request options.
- [ ] Put provider/model selection behind an interface so a free/quota-limited provider or local model can be swapped without rewriting product logic.
- [ ] Add AWS budget/cost alerts and a way to disable expensive jobs quickly.
- [ ] Do not claim the $50 AWS credit covers all possible usage; confirm credit eligibility and actual account spend.

---

# 5. What the Coding Agent Should Do Next — Static Code Changes Only When Asked

For the next agent task, provide this checklist and ask for a **source-only implementation plan**, not an unbounded rewrite.

- [ ] Do not rerun the full local Docker stack or assume local services are available; the owner develops locally but tests/runs the current application on a remote server.
- [ ] Do not alter remote infrastructure, deploy, rotate secrets, delete volumes, reindex production data, or spend AWS credits unless a separate explicit task authorizes it.
- [ ] For each proposed change, list target files, schema/API changes, backward-compatibility implications and migration needs.
- [ ] Keep existing working RAG/agentic retrieval intact unless a change is directly required by the MVP feature.
- [ ] Implement in small isolated PR-sized steps; do not combine historical backfill, auth, billing, UI and Paper Compiler into one implementation.
- [ ] Before code changes begin, agree on the MVP sequence: **P0 ingestion + paper-scoped retrieval → Paper Deep Dive → topic radar → project-to-paper match → pilot feedback → authentication/quotas/billing as needed**.

---

# 6. Documentation to Write After the Feature Plan Is Agreed

Do not write aspirational documentation for features that do not yet exist. Once the actual implementation scope is agreed and source code is updated, create/update these documents from the real code:

- [ ] `ARCHITECTURE.md` — actual services, data flow, boundaries and deployment modes.
- [ ] `API_REFERENCE.md` — registered routes, request/response schemas, errors and example calls.
- [ ] `INGESTION_AND_BACKFILL.md` — daily fetch, historical backfill, paging, rate limits, checkpoints, version updates and retries.
- [ ] `SEARCH_AND_RAG.md` — chunk schema, metadata filters, BM25/vector/RRF ranking and paper-scoped retrieval.
- [ ] `PAPER_DEEP_DIVE.md` — brief schema, evidence/citation policy, caching and failure cases.
- [ ] `EVALUATION.md` — query/answer test set, retrieval metrics, citation correctness and hallucination checks.
- [ ] `DEPLOYMENT_AND_COSTS.md` — which services run locally/remotely, required environment variables, cost controls and safe shutdown.
- [ ] `SECURITY_AND_PRIVACY.md` — auth, data ownership, secrets, deletion and public API exposure.
- [ ] `PRODUCT_AND_BILLING.md` — write only after the subscription model and quotas are implemented.

---

# 7. Boundary of This Review

This file records static source findings from the repository's `main` branch. It does **not** claim the running remote system is broken, and it does not replace the owner's successful runtime tests. If deployed code differs from GitHub `main`, reconcile the branch/commit first and update the inventory against that exact source snapshot.
