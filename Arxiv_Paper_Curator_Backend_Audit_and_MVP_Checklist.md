# Arxiv Paper Curator — Backend Audit & Lean MVP Checklist

**Purpose:** Use this checklist with coding agents to establish what is genuinely implemented in the repository, what is only described in the README, what is incomplete, and what is needed for a lean product that AI/ML engineers and AI startups can try.

**Important:** This is an audit and planning document, not a request to rewrite the codebase immediately. First complete the audit and return the evidence-based report. Product and technical documentation will be written after the audit results are reviewed.

---

## 0. Project constraints and product direction

Keep these constraints in scope while auditing and recommending changes:

- [ ] Primary audience: AI/ML engineers and AI startups who want to stay current with AI/ML research.
- [ ] Product direction: **AI Research Intelligence**, not just a generic arXiv chatbot.
- [ ] MVP workflows:
  1. **Personalized Paper Radar** — discover relevant new and historical AI/ML papers.
  2. **Paper Deep Dive** — structured brief and evidence-grounded Q&A for one paper.
  3. **Project-to-Paper Match** — explain which papers may be relevant to a user's engineering project and why.
- [ ] Founder constraints: student-led project, no dedicated GPU, approximately **US$50 AWS credits**. Do not assume the credits cover every AWS service or all ongoing usage.
- [ ] Prefer metadata-first indexing, selective/on-demand PDF parsing, caching, usage caps, and low-cost scheduled jobs.
- [ ] Do not recommend running the full Docker Compose stack continuously in the cloud by default. Local development/demo can retain the larger stack.
- [ ] Do not build enterprise features, autonomous code execution, a full literature-review agent, or a complex billing system unless evidence shows they are needed now.
- [ ] Do not add a new service/library just because it is popular. Explain its MVP need, operating cost, and simpler alternatives.

## 1. Instructions for the coding agent completing this checklist

### Audit rules

1. **Audit first; do not implement changes during the first pass.** Do not silently refactor code, add dependencies, change schemas, or rewrite documentation. Report suggested changes separately.
2. The README is a claim to verify, not proof of implementation. Inspect actual source files, configuration, tests, and execution paths.
3. Every item marked **Implemented** must include evidence: file path plus class/function/route/config key, and preferably a test or command confirming it.
4. Use **Partial** when a code path exists but has gaps, is untested, is only available in a notebook, or does not work end-to-end.
5. Use **Missing** only after searching the codebase and relevant config. Use **Not applicable** with a reason.
6. Do not print secrets, tokens, credentials, private endpoints, or contents of `.env`. It is fine to report that a secret is present/missing by variable name.
7. Run safe, relevant tests and checks. Do not run destructive reset commands, delete volumes/data, or make paid cloud calls without explicit permission.
8. If a service cannot be started in the current environment, record the blocker and distinguish “not verified” from “missing.”
9. Do not claim retrieval quality, citation correctness, uptime, or production readiness without evidence.
10. Do not expose private chain-of-thought. For agent traces, report user-safe workflow events/actions, retrieval attempts, cited sources, and errors—not hidden reasoning text.

### Status legend

- `[x] IMPLEMENTED` — verified in code and/or a passing test.
- `[~] PARTIAL` — exists but incomplete, untested, or only works in a limited path.
- `[ ] MISSING` — not implemented or no functional evidence found.
- `[?] UNVERIFIED` — cannot confirm due to environment, missing credentials, unavailable service, or unclear code path.
- `[N/A] NOT APPLICABLE` — not required for this MVP, with reason recorded.

For each checklist item, add a short **Evidence / gap** note. Do not mark all items in a section complete just because the main service starts.

---

# PART A — Audit what the backend already claims to have

The project README currently describes FastAPI, PostgreSQL, OpenSearch hybrid retrieval, Jina embeddings, Ollama, Redis, Langfuse, Airflow, traditional RAG, agentic RAG, and optional Telegram/Gradio interfaces. Verify every item below against the current repository.

## A1. Application structure and API contracts

- [ ] FastAPI application entry point and lifespan/startup/shutdown behavior are identified.
- [ ] Router registration is centralized and all intended endpoints are actually registered.
- [ ] `/api/v1/health` (or current equivalent) reports meaningful service health rather than only process liveness.
- [ ] Readiness checks distinguish API availability from unavailable database/search/model dependencies.
- [ ] Request and response schemas use Pydantic (or a clearly documented alternative) and reject invalid input.
- [ ] API errors return consistent, useful status codes and non-sensitive error messages.
- [ ] Pagination limits and `top_k`/result-size limits are enforced server-side.
- [ ] CORS settings are explicit and safe for local versus deployed environments.
- [ ] API route prefixes and actual request schemas match the README/examples.
- [ ] Streaming endpoint can communicate errors and completion reliably; disconnects/timeouts do not leak resources.
- [ ] OpenAPI docs load and reflect the current endpoint contracts.
- [ ] Logging is structured/useful and does not log secrets, full private documents, or unnecessary prompt contents.

**Evidence / gaps:**

## A2. arXiv ingestion and historical coverage

- [ ] arXiv client and supported search/query parameters are identified.
- [ ] Rate limiting, retry/backoff, timeouts, and transient-error handling are implemented.
- [ ] Requests are bounded and do not repeatedly fetch the same pages indefinitely.
- [ ] Ingestion is idempotent: retrying the same page/job does not create duplicate paper records or duplicate chunks.
- [ ] Canonical arXiv ID, version, title, abstract, authors, categories, submission/update dates, PDF/source URL, and license information (where available) are preserved appropriately.
- [ ] Historical date ranges/category filters can be queried; daily ingestion is not the only available discovery path.
- [ ] Incremental ingestion distinguishes recent updates/new submissions from an initial backfill.
- [ ] Job checkpoints/cursors are saved so a failed backfill can resume.
- [ ] Failures are recorded at paper/job level without causing the whole batch to be lost.
- [ ] PDF downloads are restricted to expected sources/hosts; redirects and file sizes are checked.
- [ ] Downloaded PDFs are cached and reused rather than repeatedly fetched.
- [ ] PDF parsing handles malformed, scanned, oversized, or unsupported PDFs gracefully.
- [ ] Docling parser output preserves useful section headings and source/page/section metadata where available.
- [ ] Failed parsing is distinguishable from “paper has no full text.”
- [ ] Airflow DAGs and tasks described in the README exist and actually invoke the reusable ingestion code.
- [ ] It is possible to run an appropriate small ingestion task locally without running an entire historical backfill.
- [ ] Data acquisition and extracted-text storage/redistribution assumptions are reviewed against paper licensing/terms.

**Evidence / gaps:**

## A3. PostgreSQL data layer

- [ ] Actual schema/models and relationships are identified.
- [ ] Primary keys, unique constraints, and indexes support paper ID/version and common search/filter queries.
- [ ] Session/connection lifecycle and connection-pool behavior are correct.
- [ ] Schema creation/migration approach is known and repeatable for a fresh database.
- [ ] Transactions and rollback behavior are handled for partially failed writes.
- [ ] Paper metadata updates do not accidentally erase previously extracted data.
- [ ] The database does not store generated briefs without an associated paper ID/version, model/prompt version, and generation status where relevant.
- [ ] User/private data (if present) has an explicit ownership model and cannot be queried across users accidentally.
- [ ] Backup/restore approach is known for any persistent deployed data.

**Evidence / gaps:**

## A4. OpenSearch, embeddings, and hybrid retrieval

- [ ] Index mappings and index creation/migration logic are identified.
- [ ] Search fields include the intended paper metadata and text fields (e.g., title, abstract, section/chunk content, categories, dates, arXiv ID/version).
- [ ] BM25 search works independently of embedding service availability.
- [ ] Vector dimension/model configuration matches the embedding model actually used.
- [ ] Embedding requests have timeouts, bounded batching, rate-limit handling, and errors recorded.
- [ ] Hybrid retrieval combines lexical and semantic results using the intended RRF/ranking logic.
- [ ] Filters such as category/date/paper ID are applied correctly and do not leak into unrelated results.
- [ ] Result pagination, deduplication, highlighting, and score handling are verified.
- [ ] Indexing is idempotent; re-indexing an updated paper version does not leave confusing duplicates.
- [ ] Index failures and partial indexing are detectable; recovery/reindex procedure is known.
- [ ] Search still works with BM25-only fallback when embeddings are unavailable.
- [ ] Retrieval returns stable source identifiers and enough metadata to cite the exact paper/chunk.
- [ ] There is a measured retrieval test set; hybrid search is not assumed superior without comparing it to BM25-only.
- [ ] If tenant/user-specific documents exist, retrieval filters enforce ownership at the query layer, not only in the UI.

**Evidence / gaps:**

## A5. Traditional RAG and citation grounding

- [ ] Actual retrieval-to-generation path is identified end-to-end.
- [ ] Prompt construction includes only bounded, relevant context and respects model context limits.
- [ ] Generated answers return source paper URLs/IDs and preferably section/page/chunk references.
- [ ] Claims can be traced to retrieved source passages; citations are not simply appended generic links.
- [ ] The API clearly distinguishes “not found in the retrieved text” from a confident answer.
- [ ] Unsupported details are not invented when source text lacks metrics, code links, compute requirements, or limitations.
- [ ] Empty retrieval, malformed chunks, model timeout, model-not-found, and provider failure have safe handling.
- [ ] Streaming and non-streaming results follow compatible response/citation contracts where intended.
- [ ] Response cache key includes all answer-affecting parameters (query, search mode, categories/paper, model and other relevant options).
- [ ] Cached answers are invalidated or versioned when paper content, prompt, model, or output schema changes as appropriate.
- [ ] User-specific or private-context responses cannot be reused across users through a shared cache key.
- [ ] Generation has explicit timeout, output-size/token limit, and bounded concurrency.

**Evidence / gaps:**

## A6. Agentic RAG / LangGraph workflow

- [ ] Scope validation is implemented and its intended scope is documented in code/config.
- [ ] Out-of-scope or general questions follow the documented path without unnecessary retrieval.
- [ ] Relevance grading has a structured result/schema and failure behavior.
- [ ] Query rewriting is bounded and does not create unlimited loops.
- [ ] Maximum retrieval attempts/recursion depth are configured and tested.
- [ ] The graph handles empty results, model errors, malformed grader output, and exhausted retries.
- [ ] User-visible `reasoning_steps` (if returned) describe workflow actions, not hidden chain-of-thought.
- [ ] Trace IDs link API response to logs/observability records without exposing secrets.
- [ ] Agentic RAG is compared against traditional RAG on a small fixed query set for answer quality, latency, and cost.
- [ ] The agentic endpoint is only enabled where it provides measurable value; it is not automatically used for every request.

**Evidence / gaps:**

## A7. Ollama/model provider configuration

- [ ] Model name and endpoint are configuration-driven rather than hard-coded in routes.
- [ ] Startup or request behavior handles unavailable Ollama/model-not-found without hanging indefinitely.
- [ ] Timeouts and retry behavior are bounded; retries do not multiply expensive generation unintentionally.
- [ ] Output parsing and structured outputs handle invalid model responses.
- [ ] Provider/model can be switched without changing product API contracts.
- [ ] Local CPU inference performance is measured on a realistic query; no GPU is assumed.
- [ ] Model response quality is evaluated on scientific/technical questions, not just whether the endpoint returns text.

**Evidence / gaps:**

## A8. Redis caching and observability

- [ ] Redis is optional or failure-tolerant if the product can serve a request without cache.
- [ ] TTL and cache invalidation behavior are configured.
- [ ] Cache keys cannot mix users/private documents and include answer-affecting options.
- [ ] Langfuse traces are created for intended operations and failures are observable.
- [ ] Observability is optional/configurable for environments where it is not deployed.
- [ ] Logs/traces avoid API keys, credentials, and unnecessary private content.
- [ ] Metrics or logs capture ingestion counts/failures, parse failures, retrieval latency, generation latency, cache hits, token/usage estimates, and error rates where available.
- [ ] Monitoring stack is not required to run the minimal public MVP if that would exceed budget/complexity.

**Evidence / gaps:**

## A9. Optional interfaces and integrations

- [ ] Telegram integration exists and is disabled unless explicitly configured.
- [ ] Gradio interface starts using documented commands and points to the correct API/config.
- [ ] Integrations reuse application services instead of duplicating ingestion/RAG logic.
- [ ] No bot token or public credential is committed to the repository.
- [ ] Optional integrations do not block the core API from starting if disabled or misconfigured.

**Evidence / gaps:**

## A10. Tests and developer workflow

- [ ] Unit, API, and integration test locations are identified.
- [ ] Fresh environment setup works using the documented package manager and supported Python version.
- [ ] The Python version required by `pyproject.toml`, Dockerfile, and CI is consistent.
- [ ] Tests can run without real paid provider calls wherever practical (mocks/fakes are used).
- [ ] Tests cover error cases, not only successful happy paths.
- [ ] Test suite results are captured with command and pass/fail counts.
- [ ] Formatting/lint/type checks exist or gaps are reported.
- [ ] Docker Compose health checks and dependency readiness are verified.
- [ ] README instructions are checked against the current repository; stale commands/ports/endpoints are listed.

**Evidence / gaps:**

---

# PART B — Required product-layer additions for the lean MVP

Do not mark an item implemented merely because a similar technical primitive exists. For example, a paper search endpoint alone does not implement personalized paper radar.

## B1. Minimal product data model

- [ ] **Paper identity/version:** canonical arXiv ID, version, metadata, dates, categories, source URL, ingestion status, full-text availability, and parser/index status.
- [ ] **Topic tracking:** user-defined topics or saved search criteria, including category/keyword/date constraints as appropriate.
- [ ] **Project profile:** short project description, technology stack, goals, constraints, and optional preferred topics.
- [ ] **Paper-to-project match:** paper ID, project ID, relevance score/label, explanation, and match timestamp/model version.
- [ ] **Paper brief:** paper ID/version, structured output, source references, model and prompt/schema version, status, created/updated timestamps.
- [ ] **Saved papers/collections:** ownership, paper references, notes, and timestamps.
- [ ] **Feedback:** relevant/not relevant, useful/not useful, and optional correction/comment tied to paper/brief/answer.
- [ ] **Digest/job status:** run date, user/topic, papers included, success/failure, and retry state.
- [ ] **Usage counters:** requests, deep dives, PDF parses, and generation usage by user or pilot account.
- [ ] Schema has migrations/unique constraints and is testable from an empty database.
- [ ] A minimal user identity/ownership approach is selected before private saved state is exposed to multiple users. Do not build complex organizations/SSO for the first MVP.

**Evidence / gaps:**

## B2. Paper Radar workflow

- [ ] User can choose or edit topics of interest.
- [ ] User can provide a project description and receive papers relevant to that project.
- [ ] Feed includes both recent papers and matching historical papers; it is not restricted to today's arXiv submissions.
- [ ] Ranking uses inexpensive metadata/keyword/category filters first, then semantic similarity if available.
- [ ] Ranking gives a useful human-readable reason for relevance; do not claim a paper improves a system unless the evidence supports that claim.
- [ ] Paper list supports pagination, date filters, category filters, deduplication, and links to the original source.
- [ ] The product clearly labels publication/submission date and arXiv version when known.
- [ ] User can save/dismiss a paper and that feedback can inform later ranking.
- [ ] Empty feeds and topics with no matches have useful handling.
- [ ] Recent-paper ingest is incremental, idempotent, and rate-limited.
- [ ] Daily digest can be manually triggered in development and scheduled in the deployment environment.

**Evidence / gaps:**

## B3. Paper Deep Dive workflow

- [ ] User can request a brief for a specific indexed paper.
- [ ] Brief generation is on-demand, not run for every paper automatically.
- [ ] PDF/source download and parsing are cached and reused.
- [ ] Brief has a stable structured schema with at least: problem, proposed method, key evidence/results, limitations, implementation/code availability, and unanswered questions.
- [ ] Facts are tied to source passages/sections/pages when the parser makes those references available.
- [ ] The output distinguishes author-reported results from the system's own interpretation or suggested experiment.
- [ ] If only metadata/abstract is available, the UI/API states the brief is abstract-only; it must not pretend the full paper was analyzed.
- [ ] Missing metrics, code, compute details, or ablations are labelled as not reported/not found rather than invented.
- [ ] User can ask questions scoped to that paper and receive cited answers.
- [ ] Questions outside the paper's evidence are acknowledged instead of answered with fabricated paper-specific claims.
- [ ] Brief cache is keyed by paper version and relevant model/prompt/schema versions.
- [ ] Limits exist for PDF size, parse time, input length, output length, and concurrent deep dives.
- [ ] A failed parse/model call can be retried safely and does not leave a permanent false-success status.

**Evidence / gaps:**

## B4. Project-to-Paper Match

- [ ] User can create/edit a basic project profile.
- [ ] Initial matching works with low-cost filters and existing metadata/abstract search.
- [ ] Semantic embeddings/LLM analysis are only used where they add value and are available.
- [ ] Each recommendation explains the match (e.g., same task, technique, metric, or deployment constraint).
- [ ] Recommendations distinguish foundational/background work from potentially actionable new work.
- [ ] The system identifies uncertainty and does not treat similarity as proof that a method will work for the project.
- [ ] User can mark a recommendation relevant/not relevant.
- [ ] Ranking feedback is stored and can be inspected in the pilot.
- [ ] A small evaluation set tests whether the top-ranked papers are actually relevant.

**Evidence / gaps:**

## B5. Historical papers and indexing strategy

- [ ] Historical metadata backfill is supported separately from daily incremental ingestion.
- [ ] Initial corpus scope is explicit (e.g., selected AI/ML categories and years) and can expand later.
- [ ] Backfill is resumable, rate-limited, idempotent, and logs progress/failures.
- [ ] Initial scale target is configurable (suggestion: start with 5,000–10,000 relevant metadata records; do not treat this as full coverage).
- [ ] The system supports a targeted lookup for a paper not yet in the local corpus.
- [ ] Full text is selectively downloaded/parsed on demand or by a deliberately chosen small allowlist.
- [ ] PDF/source storage is bounded and has an eviction/retention policy if local disk is used.
- [ ] Different versions of the same arXiv work are not accidentally presented as unrelated papers.
- [ ] The UI/source links direct users to the authoritative paper page.
- [ ] Corpus coverage and limitations are visible in the README/product copy (no claim of “all AI research” without evidence).

**Evidence / gaps:**

## B6. Minimal API surface for the MVP

Verify existing endpoints first; do not create duplicate routes if equivalent functionality already exists. Route names below are suggestions, not mandatory naming.

- [ ] `GET /health` or current health/readiness equivalent.
- [ ] Paper search/list endpoint with query, categories, date range, pagination, and source links.
- [ ] Paper detail endpoint by canonical paper ID/version.
- [ ] Topic create/list/update/delete operations.
- [ ] Project profile create/list/update/delete operations.
- [ ] Project-to-paper matches endpoint.
- [ ] Paper brief generation/retrieval endpoint.
- [ ] Paper-scoped Q&A endpoint.
- [ ] Save/dismiss/feedback endpoint.
- [ ] Digest preview/manual trigger endpoint or an equivalent internal workflow.
- [ ] Usage/status endpoint for pilot accounts or internal monitoring.
- [ ] Request/response examples and validation tests exist for every public endpoint.

**Evidence / gaps:**

## B7. Basic identity, authorization, and abuse protection

- [ ] Decide whether the first demo is single-user/private beta or multi-user public MVP. Record the decision.
- [ ] If multiple users are supported, identity/authentication is implemented with a maintained solution rather than improvised password handling.
- [ ] Private projects, saved papers, briefs, and usage records are scoped to the authenticated user.
- [ ] Authorization is enforced on the backend for every user-owned resource, not merely in frontend code.
- [ ] Rate limits and per-user request quotas protect expensive PDF/LLM operations.
- [ ] Maximum request sizes, file sizes, query lengths, and concurrency limits are explicit.
- [ ] CORS and allowed origins are appropriate for the deployed frontend.
- [ ] Secrets are supplied through environment/secret management and never committed.
- [ ] If user-uploaded documents are not in MVP scope, upload endpoints are disabled/not exposed.
- [ ] If uploads are later enabled, document isolation, file validation, retention/deletion, and prompt-injection-safe handling are separately reviewed.
- [ ] User-facing privacy/data-retention expectations can be stated truthfully.

**Evidence / gaps:**

## B8. Cost, performance, and resource controls

- [ ] No assumption that a GPU is available.
- [ ] A benchmark records CPU/local model latency on the current development hardware, if local inference remains an option.
- [ ] Deployed MVP does not require always-on Airflow + OpenSearch + Ollama + Langfuse + Redis solely to serve a small pilot.
- [ ] A lean deployment plan is documented as a recommendation only (not applied during audit).
- [ ] Daily ingestion has bounded records/pages/runtime and avoids processing the same papers repeatedly.
- [ ] Full PDF parsing and deep-dive generation are on-demand or bounded jobs.
- [ ] Cache policy avoids duplicate calls but does not return stale/wrong/private responses.
- [ ] Model/provider requests have token/output limits, timeouts, bounded retries, and concurrency limits.
- [ ] Basic usage/cost telemetry is available per generation or user where feasible.
- [ ] AWS Budgets/cost alerts are configured or listed as an explicit manual setup task; alerts are not treated as a hard spending cap.
- [ ] All unused public endpoints/ports and unneeded cloud resources can be disabled.
- [ ] Exact cloud services, region, instance class, storage assumptions, and estimated monthly cost are stated before deploying paid resources.
- [ ] Do not put credentials, access keys, customer data, or billing details into audit output.

**Evidence / gaps:**

## B9. Minimum quality evaluation

- [ ] Create a small, fixed set of representative AI/ML paper-search questions (suggestion: 30–50 to start).
- [ ] For each query, mark at least a few expected relevant papers or source passages manually.
- [ ] Compare BM25-only versus hybrid retrieval on the same queries.
- [ ] Test historical discovery using known foundational papers, including a 2017 paper such as “Attention Is All You Need.”
- [ ] Check citation/source correctness manually for generated briefs and answers.
- [ ] Include unanswerable questions and verify the model says evidence is missing.
- [ ] Include malformed PDF, empty retrieval, provider timeout, and unavailable embedding service cases.
- [ ] Measure top-k relevance with a documented simple metric or an explicit manual rubric; do not make unsupported accuracy claims.
- [ ] Measure median/95th-percentile latency on the small pilot where practical.
- [ ] Estimate cost per paper brief/deep dive and record the model/provider assumptions.
- [ ] Capture user feedback on relevance and usefulness during the pilot.

**Evidence / gaps:**

## B10. Deployment readiness for a low-budget pilot

- [ ] App runs locally from a clean checkout with the documented steps.
- [ ] Deployment needs only the minimum services necessary for the MVP workflow.
- [ ] Secrets/configuration are validated at startup and have no production defaults.
- [ ] Liveness/readiness and dependency-failure behavior are defined.
- [ ] Database migrations/init process is repeatable.
- [ ] Logs provide enough information to diagnose failures without exposing secrets/user content.
- [ ] A rollback/redeploy path is known.
- [ ] Persistent data backup/export strategy is identified before storing paying users' data.
- [ ] Cost alerts and a teardown/disable checklist exist for cloud experiments.
- [ ] Public demo is clear about beta status, corpus coverage, known limits, and whether reports are AI-generated.

**Evidence / gaps:**

---

# PART C — Priority decisions

Use these priorities when writing the gap report. Adjust them only with a reason.

## P0 — Required before a credible MVP pilot

- [ ] Verify core API and paper ingestion/search paths end-to-end.
- [ ] Correct/usable historical metadata lookup for selected AI/ML areas.
- [ ] Paper Radar flow using topics/project profile and explainable relevance.
- [ ] On-demand Paper Deep Dive with evidence-linked citations and explicit missing-data handling.
- [ ] Basic Project-to-Paper Match workflow.
- [ ] Bounded model/PDF calls, caching, timeouts, rate limits, and usage caps.
- [ ] Basic identity/ownership if multiple people can save personal data; otherwise keep demo private until this exists.
- [ ] Small test/evaluation set and a working deployed or reproducible demo.
- [ ] AWS/cloud spend controls and a written cost assumption.

## P1 — Add only after the main workflow works

- [ ] Scheduled email/Telegram digest and delivery preferences.
- [ ] Rich collections, annotations, export, and comparison of multiple papers.
- [ ] More source integrations (e.g., additional scholarly metadata and code/benchmark links).
- [ ] Better relevance feedback/ranking personalization.
- [ ] Basic paid pilot/usage billing if free pilots show repeated use and willingness to pay.
- [ ] Improved evaluation dashboards and model/provider comparison.

## P2 — Deliberately defer for now

- [ ] Enterprise SSO, audit-compliance packages, organization hierarchy, and self-hosting offer.
- [ ] Always-on full Airflow/OpenSearch/Ollama/Langfuse production deployment on a tiny budget.
- [ ] Autonomous code execution, one-click reproduction, or writing/running code against customer infrastructure.
- [ ] Full systematic literature review automation across all scholarly databases.
- [ ] Claiming complete coverage of all AI/ML papers.
- [ ] Complex usage-based billing before any validated paid demand.

---

# PART D — Test commands and evidence to collect

The agent must inspect project scripts first and use the correct commands for this repository. Do not blindly execute commands that reset data or volumes.

- [ ] Record Git branch and working-tree status before auditing.
- [ ] Record Python/package-manager versions and repository-required Python version.
- [ ] Run unit tests; report exact command, pass/fail count, and failures.
- [ ] Run API tests that do not require paid external calls.
- [ ] Run lint/format/type checks if configured.
- [ ] Run `docker compose config` or equivalent config validation if safe and available.
- [ ] Check Docker Compose service health/status only if the environment is already available; do not automatically rebuild/pull all services.
- [ ] Verify health, paper list/search, paper detail, traditional RAG, and agentic RAG paths where prerequisites allow.
- [ ] Verify the historical lookup path on a known old paper and a recent paper.
- [ ] Verify provider-down / embedding-down / empty-results behavior using mocks or safe tests.
- [ ] List untested components and the exact blocker for each.

---

# PART E — Required report from the coding agent

Return the completed checklist with the following summary **before changing code**:

## E1. Executive summary

- Total items checked.
- Count of `IMPLEMENTED`, `PARTIAL`, `MISSING`, `UNVERIFIED`, and `NOT APPLICABLE`.
- Current readiness rating for: local engineering demo, small private beta, public MVP (explain each rating).
- Top five risks/blockers.

## E2. Verified current backend inventory

For each claimed capability, provide:

| Capability | Status | Evidence (path + symbol) | Test/command result | Limitation |
|---|---|---|---|---|
| FastAPI/core API | | | | |
| arXiv ingestion | | | | |
| Historical lookup/backfill | | | | |
| PDF parsing | | | | |
| PostgreSQL | | | | |
| OpenSearch BM25 | | | | |
| Vector/hybrid retrieval | | | | |
| Traditional RAG/citations | | | | |
| Agentic RAG | | | | |
| Redis cache | | | | |
| Langfuse/observability | | | | |
| Airflow jobs | | | | |
| Tests/CI | | | | |

## E3. Missing work ranked by priority

For every recommended change, provide:

- Priority: P0/P1/P2.
- User/product outcome it enables.
- Current blocker and evidence.
- Minimal suggested implementation.
- Files likely to change.
- Dependencies/services required.
- Risks and acceptance criteria.
- Approximate complexity: S/M/L (not a time promise).

## E4. MVP architecture recommendation

Show the smallest practical architecture for a pilot under the constraints in Part 0. Distinguish services that must run in production from services that can remain local/dev-only. Include a cost-risk note; do not assert an AWS monthly price without current configuration and pricing assumptions.

## E5. Test and quality report

Include exact commands, output summaries, failed tests, external-service blockers, and the state of citations/retrieval evaluation. Do not report “all tests pass” if a test subset was skipped.

## E6. Unknowns and decisions requiring owner input

List only decisions that cannot reasonably be inferred from the code/repository. Do not block the audit on cosmetic product choices.

## E7. No-change confirmation

Confirm whether source files, configuration, dependencies, databases, and cloud resources were modified during the audit. Expected result for this audit pass: **no implementation changes**.

---

# PART F — Documentation to write after the audit is reviewed

Do **not** write these full documents during the audit pass. Once the completed checklist and gap report are returned, use them to write accurate, repository-specific documentation.

- [ ] Product brief / MVP scope and non-goals.
- [ ] Architecture overview and component/data-flow diagrams.
- [ ] Local development setup and environment-variable reference.
- [ ] API reference with request/response examples and error contracts.
- [ ] Data model/schema and migration guide.
- [ ] arXiv ingestion, historical backfill, rate-limit, retry, and recovery runbook.
- [ ] Search/RAG design, citation behavior, and evaluation methodology.
- [ ] Paper Deep Dive schema and evidence/uncertainty rules.
- [ ] Project-to-Paper Match ranking logic and evaluation notes.
- [ ] Deployment guide for the lean MVP and cloud-cost controls.
- [ ] Security, secrets, privacy, retention, and source/licensing notes.
- [ ] Troubleshooting/runbook for common failures.
- [ ] Pilot user guide and known limitations.
- [ ] Contribution guide and an explicit repository license decision.

---

## Definition of done for this checklist

The checklist is ready to return for review when the coding agent has:

1. Inspected the actual code/config/tests (not just the README).
2. Added status and evidence notes to each applicable checklist item.
3. Run safe tests and recorded results.
4. Produced the report in Part E.
5. Made no source-code or infrastructure changes during the audit pass.

**After receiving the completed checklist, review the P0 gaps first. Then implement in small slices and write the final documentation from verified behavior—not from planned features.**
