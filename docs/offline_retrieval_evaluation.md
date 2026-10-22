# Offline retrieval evaluation (Phase 4C)

This benchmark compares frozen Project-to-Paper Match and Research Radar
rankings against human-reviewed, graded relevance judgments. The evaluator is a
standalone Python standard-library tool: it imports no application code and does
not call the API, OpenSearch, PostgreSQL, arXiv, or an LLM.

The example query templates in `benchmarks/ai_ml_research_v1/queries.json` are
realistic AI/ML use cases but are **unjudged templates**, not ground truth. Their
separate `judgments.json` contains `annotation_status: "unjudged"`; no production
baseline or relevance label is claimed. Synthetic fixtures live under
`tests/fixtures/retrieval_eval/` and exist only to test metric calculations.

## Versioned input format 1.0

Keep three files separate so query cases, human labels, and captured system runs
can evolve independently. All three use:

```json
{"format_version":"1.0","benchmark_id":"ai-ml-research-discovery","benchmark_version":"1.0.0"}
```

`queries.json` adds `cases`. A case has a stable `case_id`, `query_type`
(`project_match` or `research_radar`), a type-specific `query` object, and
optional `expected_filters` (`categories`, inclusive ISO `date_from` and
`date_to`). Project queries carry the project description and optional title,
technologies, or research interests. Radar queries carry 1–8 topics. Do not
change a case's meaning while retaining its ID; make a new ID/version when the
query materially changes.

`judgments.json` adds `annotation_provenance` and `cases`. A judgment record is
keyed by `case_id`, `target`, and optional `topic_id`. Targets are `project_match`,
`radar_fused`, and `radar_topic`. Each record must declare `annotation_status`
as `judged` or `unjudged`. A judged record has a list of exact `arxiv_id`
strings, integer `relevance` from 0 to 3, and a short human-authored `rationale`.
An unjudged record has an empty list. For radar topic-level evaluation, make a
separate record for each topic. IDs are compared exactly; version suffixes are
never stripped or merged.

`rankings.json` adds frozen `rankings`. Each run has `case_id`, `target`, optional
`topic_id`, `retrieval_method`, optional `metadata_snapshot`, and ordered
`results`. Each result has exact `arxiv_id`, positive `rank`, and optional
`retrieval_score`. Scores are retained as provenance only, never compared or
used by the metrics. Duplicate exact IDs or ranks within a run are rejected;
different versions are separate documents. Radar topic-level runs use the same
format as fused runs but set `target` to `radar_topic` and `topic_id` to one of
the case's topics.

The validator checks the versions match, cases and targets exist, radar topics
match their case, relevance grades and ranks are bounded/valid, and duplicate
IDs are absent. The evaluator supports up to 1,000 results per ranking run.

## Metrics and conventions

- `DCG@k = sum((2^relevance - 1) / log2(rank + 1))`; `nDCG@k = DCG@k / ideal_DCG@k`.
- `Precision@k = relevant retrieved in the first k / k` (fixed denominator,
  including unfilled result slots).
- `Recall@10 = relevant retrieved in the first 10 / all positively judged
  documents for that target`.
- `MRR@10 = 1 / rank of the first positively judged result in the first 10`,
  or zero if none is found.

An absent relevance label is **unjudged**, not a human irrelevance judgment.
For rank metrics, unjudged retrieved documents receive zero gain as a clearly
reported evaluation convention; the report includes judged-result coverage,
unjudged counts/proportions, and warnings. This convention must not be read as a
claim that those papers are irrelevant. To improve evaluation, review and label
the unjudged results. Queries with no positive relevance judgments have undefined
nDCG, Recall, and MRR (`null`) and are excluded from those metric averages; they
are counted in report exclusions. Precision remains defined under its fixed
cutoff convention. Aggregates are macro averages over eligible query targets and
are also grouped by retrieval method and target.

The metrics depend only on rank order and labels, so raw BM25, RRF, and future
retrieval scores need not share a scale. No baseline is fabricated.

## Collecting real evaluations

1. Review and version the query cases. Do not label the examples as judged until
   candidate papers have actually been reviewed.
2. In a controlled environment with an available metadata corpus, run the exact
   Phase 4A/4B request and filters. Save the returned exact versioned arXiv IDs
   and ranks without reordering, plus method and metadata snapshot/index date.
3. To evaluate Radar's per-topic candidate rankings (as distinct from its fused
   feed), capture one metadata-discovery ranking for each topic using that case's
   same category/date filters and record its exact `topic_id`. The ordinary Radar
   response is the fused-feed target; it does not expose all underlying lists.
4. Have a reviewer inspect the papers and assign a 0–3 relevance grade with a
   concise rationale. Record annotation provenance and mark only reviewed
   targets `judged`. Label relevant papers beyond the retrieved list where
   possible so Recall's denominator is meaningful.
5. Freeze all three input files, their benchmark versions, and the metadata
   snapshot before comparing retrieval methods. Use identical cases and
   judgments for fair comparisons.

No real outputs or judgments are included in this repository yet. Do not infer
retrieval quality from the synthetic tests.

## CLI

From the repository root:

```powershell
python tools/retrieval_eval.py `
  --queries benchmarks/ai_ml_research_v1/queries.json `
  --judgments benchmarks/ai_ml_research_v1/judgments.json `
  --rankings path/to/frozen_rankings.json `
  --json-out reports/retrieval-eval.json `
  --markdown-out reports/retrieval-eval.md
```

The JSON and Markdown outputs include benchmark/report versions, per-target
metrics, macro aggregates, exclusions, coverage, and data-quality warnings. The
checked-in realistic template judgments are all unjudged, so they cannot produce
a quality score until a reviewer supplies judgments and frozen rankings.
