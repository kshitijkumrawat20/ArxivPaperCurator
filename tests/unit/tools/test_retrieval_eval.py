import copy
import json
from pathlib import Path

import pytest

from tools.retrieval_eval import (
    EvaluationInputError,
    evaluate,
    evaluate_run,
    main,
    render_markdown,
    validate_inputs,
)

FIXTURE_DIR = Path("tests/fixtures/retrieval_eval")


def inputs():
    queries = {
        "format_version": "1.0",
        "benchmark_id": "metric-tests",
        "benchmark_version": "1",
        "cases": [
            {"case_id": "project", "query_type": "project_match", "query": {"project_description": "synthetic project"}},
            {"case_id": "radar", "query_type": "research_radar", "query": {"topics": ["retrieval", "reranking"]}},
        ],
    }
    judgments = {
        "format_version": "1.0",
        "benchmark_id": "metric-tests",
        "benchmark_version": "1",
        "cases": [
            {
                "case_id": "project",
                "target": "project_match",
                "annotation_status": "judged",
                "judgments": [
                    {"arxiv_id": "2401.00001v2", "relevance": 3, "rationale": "Synthetic highly relevant fixture."},
                    {"arxiv_id": "2401.00002v1", "relevance": 1, "rationale": "Synthetic partially relevant fixture."},
                ],
            },
            {
                "case_id": "radar",
                "target": "radar_fused",
                "annotation_status": "judged",
                "judgments": [
                    {"arxiv_id": "2401.00001v2", "relevance": 2, "rationale": "Synthetic fused-feed fixture."}
                ],
            },
            {
                "case_id": "radar",
                "target": "radar_topic",
                "topic_id": "retrieval",
                "annotation_status": "judged",
                "judgments": [
                    {"arxiv_id": "2401.00002v1", "relevance": 1, "rationale": "Synthetic topic-level fixture."}
                ],
            },
        ],
    }
    rankings = {
        "format_version": "1.0",
        "benchmark_id": "metric-tests",
        "benchmark_version": "1",
        "rankings": [
            {
                "case_id": "project", "target": "project_match", "retrieval_method": "synthetic-a",
                "results": [
                    {"arxiv_id": "2401.00002v1", "rank": 1, "retrieval_score": 9999},
                    {"arxiv_id": "2401.00001v2", "rank": 2, "retrieval_score": 0.0001},
                    {"arxiv_id": "2401.00001v1", "rank": 3, "retrieval_score": 100},
                ],
            },
            {
                "case_id": "radar", "target": "radar_fused", "retrieval_method": "synthetic-a",
                "results": [{"arxiv_id": "2401.00001v2", "rank": 1}],
            },
            {
                "case_id": "radar", "target": "radar_topic", "topic_id": "retrieval", "retrieval_method": "synthetic-a",
                "results": [{"arxiv_id": "2401.00002v1", "rank": 1}],
            },
        ],
    }
    return queries, judgments, rankings


def test_ndcg_graded_gain_and_ordering_are_correct():
    _, judgments, rankings = inputs()
    measured = evaluate_run(rankings["rankings"][0], judgments["cases"][0])
    ideal_dcg = 7 + 1 / 1.584962500721156
    observed_dcg = 1 + 7 / 1.584962500721156
    assert measured["metrics"]["ndcg@5"] == pytest.approx(observed_dcg / ideal_dcg)
    assert measured["metrics"]["ndcg@10"] == pytest.approx(observed_dcg / ideal_dcg)
    assert measured["metrics"]["ndcg@5"] < 1.0


def test_precision_recall_mrr_and_cutoff_behavior():
    _, judgments, rankings = inputs()
    measured = evaluate_run(rankings["rankings"][0], judgments["cases"][0])
    assert measured["metrics"]["precision@5"] == pytest.approx(2 / 5)
    assert measured["metrics"]["precision@10"] == pytest.approx(2 / 10)
    assert measured["metrics"]["recall@10"] == 1.0
    assert measured["metrics"]["mrr@10"] == 1.0

    late = {"results": [{"arxiv_id": f"nonrelevant.{index}", "rank": index} for index in range(1, 11)] + [
        {"arxiv_id": "2401.00001v2", "rank": 11}
    ]}
    late_metrics = evaluate_run(late, judgments["cases"][0])["metrics"]
    assert late_metrics["precision@10"] == 0
    assert late_metrics["recall@10"] == 0
    assert late_metrics["mrr@10"] == 0


def test_empty_rankings_no_relevant_judgments_and_unjudged_coverage_are_explicit():
    judgment = {"judgments": [{"arxiv_id": "known.v1", "relevance": 0}]}
    empty = evaluate_run({"results": []}, judgment)
    assert empty["metrics"]["ndcg@10"] is None
    assert empty["metrics"]["recall@10"] is None
    assert empty["metrics"]["mrr@10"] is None
    assert empty["metrics"]["precision@10"] == 0
    assert empty["metrics"]["judged_result_coverage"] is None
    assert empty["no_relevant_judgments"]

    judged = {"judgments": [{"arxiv_id": "known.v1", "relevance": 2}]}
    ranking = {"results": [{"arxiv_id": "unknown.v1", "rank": 1}, {"arxiv_id": "known.v1", "rank": 2}]}
    partial = evaluate_run(ranking, judged)
    assert partial["counts"]["unjudged_retrieved"] == 1
    assert partial["metrics"]["judged_result_coverage"] == 0.5
    assert partial["metrics"]["unjudged_result_proportion"] == 0.5
    assert partial["metrics"]["ndcg@10"] < 1.0  # zero-gain convention is visible in the report


def test_exact_versions_are_distinct_duplicate_ids_and_malformed_fields_rejected():
    queries, judgments, rankings = inputs()
    # Different versions coexist, but a duplicate exact ID in one ranking is invalid.
    validate_inputs(queries, judgments, rankings)
    broken = copy.deepcopy(rankings)
    broken["rankings"][0]["results"].append({"arxiv_id": "2401.00001v2", "rank": 4})
    with pytest.raises(EvaluationInputError, match="duplicate exact arxiv_id"):
        validate_inputs(queries, judgments, broken)

    broken = copy.deepcopy(queries)
    broken["cases"][0].pop("query")
    with pytest.raises(EvaluationInputError, match="query must be an object"):
        validate_inputs(broken, judgments, rankings)

    broken = copy.deepcopy(queries)
    broken["cases"][0]["expected_filters"] = {"date_from": "2025-01-02", "date_to": "2025-01-01"}
    with pytest.raises(EvaluationInputError, match="date_from must be on or before"):
        validate_inputs(broken, judgments, rankings)


def test_radar_fused_and_topic_targets_validate_and_evaluate_separately():
    queries, judgments, rankings = inputs()
    report = evaluate(queries, judgments, rankings)
    assert {row["target"] for row in report["per_query"]} == {
        "project_match", "radar_fused", "radar_topic"
    }
    assert report["summary"]["evaluated_query_count"] == 3


def test_aggregate_is_macro_average_and_identical_frozen_inputs_are_stable():
    queries, judgments, rankings = inputs()
    second_run = copy.deepcopy(rankings["rankings"][0])
    second_run["retrieval_method"] = "synthetic-b"
    second_run["results"] = list(reversed(second_run["results"]))
    rankings["rankings"].append(second_run)
    report = evaluate(queries, judgments, rankings)
    assert len(report["grouped_macro_averages"]) == 4
    scores = [row["metrics"]["ndcg@10"] for row in report["per_query"] if row.get("metrics") and row["metrics"]["ndcg@10"] is not None]
    assert report["overall_macro_average"]["ndcg@10"] == pytest.approx(sum(scores) / len(scores))
    assert evaluate(queries, judgments, rankings) == report


def test_unjudged_annotation_is_excluded_not_scored_as_empty_relevance():
    queries, judgments, rankings = inputs()
    judgments["cases"][0]["annotation_status"] = "unjudged"
    judgments["cases"][0]["judgments"] = []
    report = evaluate(queries, judgments, rankings)
    project = next(row for row in report["per_query"] if row["case_id"] == "project")
    assert project["annotation_status"] == "unjudged"
    assert project["metrics"] is None
    assert project["exclusion_reason"] == "Judgment record is explicitly unjudged"


def test_fixture_is_marked_synthetic_and_cli_writes_json_and_markdown(tmp_path):
    queries = FIXTURE_DIR / "synthetic_queries.json"
    judgments = FIXTURE_DIR / "synthetic_judgments.json"
    rankings = FIXTURE_DIR / "synthetic_rankings.json"
    assert "Synthetic" in judgments.read_text(encoding="utf-8")
    json_out = tmp_path / "out" / "report.json"
    markdown_out = tmp_path / "out" / "report.md"
    result = main([
        "--queries", str(queries), "--judgments", str(judgments), "--rankings", str(rankings),
        "--json-out", str(json_out), "--markdown-out", str(markdown_out),
    ])
    assert result == 0
    report = json.loads(json_out.read_text(encoding="utf-8"))
    markdown = markdown_out.read_text(encoding="utf-8")
    assert report["summary"]["unjudged_retrieved_count"] == 1
    assert "Unjudged results receive zero gain" in markdown
    assert render_markdown(report) == markdown


def test_benchmark_templates_are_explicitly_unjudged_and_valid():
    base = Path("benchmarks/ai_ml_research_v1")
    queries = json.loads((base / "queries.json").read_text(encoding="utf-8"))
    judgments = json.loads((base / "judgments.json").read_text(encoding="utf-8"))
    rankings = {"format_version": "1.0", "benchmark_id": queries["benchmark_id"], "benchmark_version": queries["benchmark_version"], "rankings": []}
    report = evaluate(queries, judgments, rankings)
    assert len(queries["cases"]) == 4
    assert all(row["annotation_status"] == "unjudged" for row in judgments["cases"])
    assert report["summary"]["ranking_run_count"] == 0
