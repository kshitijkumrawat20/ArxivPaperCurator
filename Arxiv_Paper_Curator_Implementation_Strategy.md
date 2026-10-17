# Arxiv Paper Curator — Implementation Strategy After Static Audit

**Basis:** Static audit report for source commit `cc42c3a`, dated 2026-10-16.  
**Goal:** Convert the existing backend into a low-cost, portfolio-worthy MVP for AI/ML engineers and AI startups.  
**Constraint:** The app has already been tested by the owner on a remote server. Do not rerun or locally launch the application as part of the initial code-level work. The deployed commit may differ from the inspected source.

## 1. Product decision

Build one coherent workflow rather than three disconnected features:

> Describe an AI/ML project → discover relevant new and foundational papers → inspect a paper with evidence-backed deep dive → save or dismiss the recommendation → use feedback to improve future matches.

This packages the proposed Paper Radar, Paper Deep Dive, and Project-to-Paper Match around one engineering job-to-be-done.

## 2. What the audit says exists

The repository contains reusable building blocks: FastAPI, PostgreSQL paper metadata and parsed-text storage, an arXiv Atom client, PDF caching/Docling parsing, chunking, Jina embeddings, OpenSearch BM25/vector/hybrid search with RRF, traditional and agentic RAG, Redis answer caching, Langfuse, Airflow, plus optional Telegram/Gradio interfaces.

It does not contain the SaaS/product layer: user accounts, topic preferences, saved projects, project-to-paper recommendations, structured research briefs, saved collections, personalized digest delivery, usage metering, or billing.

The audit is static and based on commit `cc42c3a`; first reconcile that with the code version actually being edited/deployed. Do not assume findings automatically describe the remote deployment.

## 3. Prioritized implementation sequence

### Phase 0 — Source parity, no code changes

**Goal:** Make sure implementation work targets the code that was audited.

- Record local Git HEAD and working-tree changes.
- Record the remote deployment's commit SHA only if already available through deployment metadata; do not connect to or modify the server for this task.
- Compare the source under review with audit commit `cc42c3a`.
- If source differs, re-check the noted defects against the current source before applying fixes.

**Exit criteria:** The team knows which source version the work will modify, and no one claims the static audit proves deployed behavior.

### Phase 1 — Correctness blockers in the existing pipeline

Keep this package narrowly scoped; don't add product features yet.

1. Fix `HybridIndexingService.index_paper()` so all chunks are accumulated and bulk indexed outside the chunk-building loop. Add a unit test with multiple chunks that verifies every chunk is submitted and counted correctly.
2. Fix the reported short-text chunking path in `TextChunker` where the `_reconstruct_text` call has a mismatched argument count. Add a focused unit test for short text/abstract-only input.
3. Correct hybrid query semantics: apply category filters to both lexical and vector branches, and preserve pagination/offset behavior for hybrid search. Add query-construction tests.
4. Fix the feedback request/router field mismatch (`comments` vs `comment`) and add a focused API-contract/unit test.
5. Register the paper router if its list/detail endpoints are intended to be public, with a router-wiring test.
6. Review the agentic endpoint's handling of `top_k`, `use_hybrid`, and `categories`. Either pass the selected values through correctly or remove/clearly document unsupported options rather than silently ignoring them.

**Rules:** Do not rewrite working RAG architecture. Make small changes and focused tests. Do not start the application, Docker, ingestion, or external services. The owner can deploy and perform remote smoke testing separately.

**Exit criteria:** The identified source-level defects are corrected, or each has a documented reason for being deferred. Existing core modules remain reusable.

### Phase 2 — Make the corpus reliable and affordable

**Goal:** Support current AI/ML papers plus a bounded historical corpus without downloading/parsing every PDF.

- Add a configurable, bounded category strategy instead of assuming only one `cs.AI` category. Start with a small set chosen for the target audience; don't indiscriminately ingest all arXiv categories.
- Implement metadata-first ingestion: title, abstract, authors, dates, categories, arXiv identifier/version, and source URL are searchable even without parsed PDF text.
- Keep PDF download, Docling parsing, and embeddings on-demand or limited to selected/relevant papers.
- Implement bounded/resumable historical backfill using existing date and offset primitives plus a durable checkpoint/run record. Do not treat a date-range parameter alone as a backfill system.
- Fix incremental ingestion to recover missed days and respect successful-run boundaries rather than assuming a weekday-only previous-day run is complete.
- Decide and implement a canonical arXiv ID/version policy before building update logic. Preserve version provenance, avoid silently treating different versions as unrelated papers, and ensure reindexing is idempotent.
- Make indexing status/failures observable; don't let a metadata record appear full-text indexed when it has no chunks.

**MVP scope:** Seed a bounded historical selection from 2017 onward plus daily incremental metadata. Expand only when relevance/coverage needs it. Avoid bulk downloading the entire arXiv corpus.

**Exit criteria:** New and selected historical papers are searchable at metadata/abstract level; full text can be processed for selected papers; backfill can resume without duplicate growth.

### Phase 3 — Paper-scoped retrieval and evidence contract

**Goal:** Make a selected paper genuinely queryable on its own.

- Add an optional `arxiv_id`/canonical paper identifier filter through request schemas, query builder, BM25, vector/kNN, hybrid branches, and RAG/agentic retrieval.
- Add a deliberate response contract for evidence: paper ID/version, section name, stable chunk reference, and supporting excerpt where available. Do not fabricate page numbers if page provenance isn't retained.
- Ensure a paper-specific question cannot accidentally retrieve chunks from other papers.
- Keep existing cross-paper RAG as a separate capability.
- Add focused unit tests for query construction, filter propagation, empty/unindexed-paper behavior, and evidence mapping.

**Exit criteria:** A request scoped to one paper returns evidence only from that paper/version and responses expose traceable source references.

### Phase 4 — MVP workflow: Project-to-Paper Match + Paper Deep Dive

Build the minimum sellable engineering workflow.

**Project-to-Paper Match:**
- Accept a project description, technical stack, goal/problem, and optional constraints.
- Use metadata/abstract retrieval and existing hybrid search to produce candidate papers.
- Rank and deduplicate candidates; show a concise, evidence-grounded explanation of why each paper matches.
- Generate explanations only for the top few candidates to control inference cost.
- Let pilot users mark a recommendation useful/not useful; store feedback only once ownership/privacy design is clear.

**Paper Deep Dive:**
- Generate one versioned structured brief on demand: problem, method, reported experiments/metrics, limitations, available code/artifacts, engineering implications, and unknowns.
- Link claims to extracted sections/chunks or cited paper locations supported by stored data.
- Explicitly distinguish author-reported results from system-generated engineering suggestions.
- Handle `metadata_only`, `abstract_only`, `processing`, `ready`, and `failed` states rather than pretending every paper is fully parsed.
- Cache by paper/version + model + prompt/schema version; invalidate/recompute when relevant inputs change.

**Exit criteria:** A user can describe a real AI/ML project, receive useful relevant papers, open one, and ask evidence-grounded questions or generate a structured brief at controlled cost.

### Phase 5 — Minimal Paper Radar for a small pilot

Only after search relevance and deep-dive quality are credible:

- Add lightweight saved topics/project profiles and saved/dismissed papers.
- Create a “latest papers matched to my project” feed using the same candidate-ranking workflow as Phase 4.
- Add one digest channel initially (email or Telegram), not multiple integrations.
- Use the existing deployed scheduler/Airflow if it already fits; do not add a second scheduler without a concrete need.
- Track digest runs and delivery status so failed deliveries can be retried.

For the first few pilot users, manual onboarding or a restricted invite-only pilot is acceptable. Don't build complex organization/team roles prematurely.

**Exit criteria:** The user receives a relevant recurring feed, returns to review it, and can save/dismiss items.

### Phase 6 — Public-pilot safeguards and monetization

Before allowing general public sign-ups or storing private project descriptions:

- Add minimal authentication and enforce ownership checks at repository and API layers.
- Keep shared public paper data separate from private user/project/brief/feedback data.
- Add basic rate limits and request/generation quotas; meter model and embedding usage for cost visibility.
- Review secret handling, CORS/TLS, public OpenSearch exposure, and data retention/deletion.
- Add payment integration only after pilot users repeatedly use the product and at least some show real willingness to pay.

**Exit criteria:** A small invited pilot can use private project data safely; billing is added only after demand is demonstrated.

## 4. What NOT to build yet

- Do not add another vector database; reuse OpenSearch.
- Do not download and parse every historical PDF upfront.
- Do not build autonomous code execution, one-click reproduction, or agents that run customer experiments.
- Do not add full enterprise SSO, complex team roles, or billing before usage and payment intent are validated.
- Do not rewrite Airflow or the existing RAG stack solely for architectural preference.
- Do not treat README claims, function existence, or test-file existence as proof of working feature wiring.

## 5. Recommended immediate agent work package

Start with **Phase 0 followed by Phase 1 only**. Keep the PR small and ask the coding agent to:

- inspect the current source and relevant code paths;
- verify the report's findings against the current branch;
- implement only confirmed correctness fixes listed in Phase 1;
- add or update focused unit tests without launching the app or external services;
- return changed files, reasons, test commands/results, remaining uncertainties, and any behavior changes;
- make no schema, authentication, billing, frontend, or cloud changes in this package.

Review that patch before asking the agent to begin Phase 2.

## 6. Cost and scope rules

- Use the existing server and existing stack while validating; do not deploy extra always-on services without a cost estimate.
- Prefer metadata/abstract search and top-N on-demand full-text processing.
- Cache briefs and embeddings where safe and versioned.
- Keep provider calls behind existing service interfaces so the model/provider can be changed later.
- Record approximate cost per deep dive and per digest before defining free/pro usage limits.

## 7. Success criteria for the first pilot

These are suggested decision gates, not industry benchmarks:

- 10 AI/ML engineers or startup builders try the workflow on real projects.
- Users can identify at least one relevant paper they would otherwise have missed or spent significant time finding.
- They use it repeatedly over multiple weeks, not just once for novelty.
- Some users agree to pay or join a clearly scoped paid pilot.
- Retrieval/evidence quality is checked against a small manually reviewed set of representative questions.

The next milestone is not a huge corpus or a fully automated SaaS. It is a reliable, evidence-backed project-to-paper workflow that users return to and are willing to pay for.
