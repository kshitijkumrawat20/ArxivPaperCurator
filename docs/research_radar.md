# Multi-topic Research Radar (Phase 4B)

`POST /api/v1/papers/radar` returns a recent metadata-only feed for 1–8 research
topics. The request accepts optional arXiv categories, an inclusive lookback
window (1–365 days, default 30), `top_k` (1–20, default 10), and a bounded
per-topic candidate limit (1–50, default 20). Topics are whitespace-normalized
and deduplicated case-insensitively before searches. Combined normalized topic
text is limited to 500 characters.

The service makes at most one search for each normalized topic (maximum 8).
Every search reuses `MetadataDiscoveryService`, limits its candidates, and sends
the same publication-date and category filters into the metadata-index query.
The lookback window is calculated once using the current UTC date and includes
both its start and end dates. The existing metadata query builder translates the
inclusive end date to an exclusive next-day OpenSearch bound.

## Ranking and signals

BM25 scores from separate topic queries are not compared. Results are fused by
Reciprocal Rank Fusion with `k = 60`:

```text
fusion_score(paper) = sum(1 / (60 + rank_in_topic_result_list))
```

A paper contributes only for topic lists in which its exact arXiv ID appeared.
Repeated IDs within or across lists are counted once per topic; different
versioned IDs remain separate. Papers are ordered by descending fusion score,
then newest publication date, then exact arXiv ID. The fusion score is a ranking
signal, not a probability or calibrated relevance measure.

`matched_topics` records which metadata searches returned a paper. Retrieval is
not proof of technical relevance. Optional match signals are stricter: they are
short excerpts containing the literal topic phrase in the retrieved title,
abstract, or categories. No LLM-generated explanations or full-text claims are
made. Abstract excerpts are capped at 1,000 characters.

## Failures and limitations

If some topic searches fail, successful results are returned with a warning for
each failed topic; internal exception details are not exposed. If all searches
fail, the API returns HTTP 503. Successful searches with no candidates return a
normal empty result with an explanatory message.

This is lexical BM25 discovery over the metadata index, whose coverage and
freshness depend on ingestion/index synchronization. It does not download PDFs,
parse full text, create embeddings, call an LLM, persist user topics, or change
the daily Airflow schedule. Maximum work per request is 8 searches × 50
candidates. Exact arXiv versions are preserved; no canonical-version policy is
introduced.
