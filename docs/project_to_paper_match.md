# Phase 4A — Metadata-First Project-to-Paper Match

`POST /api/v1/papers/match-project` accepts a project description plus optional title, technology terms, research interests, arXiv categories, publication-date bounds, and `top_k` (1–20; default 10). Text and list inputs are normalized, category/date inputs are validated, and `date_from` must not be after `date_to`.

The backend composes a whitespace-normalized query from the supplied project text and terms, capped at 500 characters, then calls the existing `MetadataDiscoveryService`. That service searches the separate, vector-free paper metadata index and applies category and publication-date filters inside the BM25 query. Only the requested candidate count is retrieved. Results retain their exact versioned arXiv ID and metadata-index order; duplicate exact IDs are removed, but different versions are not merged.

Each result returns its BM25 retrieval rank and raw OpenSearch score, labeled explicitly as not a calibrated probability. `match_signals` are deterministic exact term/category matches with excerpts from the returned title, abstract, or categories. They are not LLM-generated explanations. Terms omitted from the bounded query are not presented as text-match signals. If no exact signal is found, the result remains ranked by BM25 without a manufactured explanation.

The endpoint performs no PostgreSQL writes, PDF download or parsing, embeddings, chunk-index retrieval, or LLM calls. Metadata-only and abstract-only papers are eligible. Empty search results return normally with `result_count: 0` and a suggestion to broaden the query/filters; metadata search failures return HTTP 503 without falling back to the global full-text index.

This first version is lexical BM25 over indexed title, abstract, and authors. It does not semantically understand project intent, calibrate relevance, rerank, or guarantee historical corpus completeness. Query matching also does not guarantee that every returned result has a literal signal because BM25 can rank using partial/fuzzy term matches. The metadata index must already contain the paper for it to be discoverable.
