#!/usr/bin/env python3
"""Offline evaluator for frozen Project Match and Research Radar rankings.

This module intentionally uses only the Python standard library and never imports
application services or contacts an external system.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

FORMAT_VERSION = "1.0"
REPORT_VERSION = "1.0"
TARGETS = {"project_match", "radar_fused", "radar_topic"}
RELEVANCE_MIN = 0
RELEVANCE_MAX = 3
MAX_RANKING_ROWS = 1000
METRIC_KEYS = (
    "ndcg@5",
    "ndcg@10",
    "precision@5",
    "precision@10",
    "recall@10",
    "mrr@10",
    "judged_result_coverage",
    "unjudged_result_proportion",
)


class EvaluationInputError(ValueError):
    """Invalid benchmark, judgments, or frozen ranking input."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise EvaluationInputError(message)


def _read_json(path: str | Path) -> dict[str, Any]:
    try:
        with Path(path).open("r", encoding="utf-8") as handle:
            value = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise EvaluationInputError(f"Could not read JSON file {path}: {exc}") from exc
    _require(isinstance(value, dict), f"Top-level JSON in {path} must be an object")
    return value


def _nonempty_string(value: Any, field: str) -> str:
    _require(isinstance(value, str) and bool(value.strip()), f"{field} must be a non-empty string")
    return value


def _valid_case(case: Any, index: int) -> tuple[str, str, dict[str, Any]]:
    label = f"queries.cases[{index}]"
    _require(isinstance(case, dict), f"{label} must be an object")
    case_id = _nonempty_string(case.get("case_id"), f"{label}.case_id")
    query_type = case.get("query_type")
    _require(isinstance(query_type, str) and query_type in {"project_match", "research_radar"}, f"{label}.query_type is invalid")
    query = case.get("query")
    _require(isinstance(query, dict), f"{label}.query must be an object")
    if query_type == "project_match":
        _nonempty_string(query.get("project_description"), f"{label}.query.project_description")
    else:
        topics = query.get("topics")
        _require(isinstance(topics, list) and 1 <= len(topics) <= 8, f"{label}.query.topics must contain 1-8 topics")
        normalized = []
        for topic_index, topic in enumerate(topics):
            normalized.append(_nonempty_string(topic, f"{label}.query.topics[{topic_index}").strip())
        _require(
            len({topic.casefold() for topic in normalized}) == len(normalized),
            f"{label}.query.topics must be unique after normalization",
        )
    filters = case.get("expected_filters", {})
    _require(isinstance(filters, dict), f"{label}.expected_filters must be an object")
    categories = filters.get("categories", [])
    _require(isinstance(categories, list) and all(isinstance(item, str) for item in categories), f"{label}.expected_filters.categories must be a list of strings")
    parsed_dates = {}
    for date_field in ("date_from", "date_to"):
        value = filters.get(date_field)
        if value is not None:
            _require(isinstance(value, str), f"{label}.expected_filters.{date_field} must be an ISO date")
            try:
                parsed_dates[date_field] = date.fromisoformat(value)
            except ValueError as exc:
                raise EvaluationInputError(f"{label}.expected_filters.{date_field} must be an ISO date") from exc
    if "date_from" in parsed_dates and "date_to" in parsed_dates:
        _require(parsed_dates["date_from"] <= parsed_dates["date_to"], f"{label}.expected_filters.date_from must be on or before date_to")
    return case_id, query_type, query


def _validate_header(document: dict[str, Any], label: str) -> tuple[str, str, str]:
    _require(document.get("format_version") == FORMAT_VERSION, f"{label}.format_version must be {FORMAT_VERSION}")
    benchmark_id = _nonempty_string(document.get("benchmark_id"), f"{label}.benchmark_id")
    benchmark_version = _nonempty_string(document.get("benchmark_version"), f"{label}.benchmark_version")
    return benchmark_id, benchmark_version, str(document["format_version"])


def validate_inputs(
    queries: dict[str, Any], judgments: dict[str, Any], rankings: dict[str, Any]
) -> tuple[dict[str, dict[str, Any]], dict[tuple[str, str, str | None], dict[str, Any]], list[dict[str, Any]]]:
    query_header = _validate_header(queries, "queries")
    judgment_header = _validate_header(judgments, "judgments")
    ranking_header = _validate_header(rankings, "rankings")
    _require(query_header[:2] == judgment_header[:2] == ranking_header[:2], "benchmark_id and benchmark_version must match across all input files")

    cases = queries.get("cases")
    _require(isinstance(cases, list) and cases, "queries.cases must be a non-empty list")
    case_by_id: dict[str, dict[str, Any]] = {}
    for index, case in enumerate(cases):
        case_id, query_type, query = _valid_case(case, index)
        _require(case_id not in case_by_id, f"Duplicate case_id: {case_id}")
        case_by_id[case_id] = {**case, "query_type": query_type, "query": query}

    judgment_rows = judgments.get("cases")
    _require(isinstance(judgment_rows, list), "judgments.cases must be a list")
    judgment_by_key: dict[tuple[str, str, str | None], dict[str, Any]] = {}
    for index, row in enumerate(judgment_rows):
        label = f"judgments.cases[{index}]"
        _require(isinstance(row, dict), f"{label} must be an object")
        case_id = _nonempty_string(row.get("case_id"), f"{label}.case_id")
        _require(case_id in case_by_id, f"{label} references unknown case_id {case_id}")
        target = row.get("target")
        _validate_target(case_by_id[case_id], target, row.get("topic_id"), label)
        topic_id = row.get("topic_id") if target == "radar_topic" else None
        key = (case_id, target, topic_id)
        _require(key not in judgment_by_key, f"Duplicate judgment key: {key}")
        status = row.get("annotation_status")
        _require(isinstance(status, str) and status in {"judged", "unjudged"}, f"{label}.annotation_status must be judged or unjudged")
        docs = row.get("judgments", [])
        _require(isinstance(docs, list), f"{label}.judgments must be a list")
        _require(status != "unjudged" or not docs, f"{label}: unjudged records cannot contain relevance labels")
        seen_ids = set()
        for doc_index, judgment in enumerate(docs):
            doc_label = f"{label}.judgments[{doc_index}]"
            _require(isinstance(judgment, dict), f"{doc_label} must be an object")
            arxiv_id = _nonempty_string(judgment.get("arxiv_id"), f"{doc_label}.arxiv_id")
            _require(arxiv_id not in seen_ids, f"{label} contains duplicate exact arxiv_id {arxiv_id}")
            seen_ids.add(arxiv_id)
            relevance = judgment.get("relevance")
            _require(type(relevance) is int and RELEVANCE_MIN <= relevance <= RELEVANCE_MAX, f"{doc_label}.relevance must be an integer from 0 to 3")
            _nonempty_string(judgment.get("rationale"), f"{doc_label}.rationale")
        judgment_by_key[key] = row

    runs = rankings.get("rankings")
    _require(isinstance(runs, list), "rankings.rankings must be a list")
    run_keys = set()
    normalized_runs = []
    for index, run in enumerate(runs):
        label = f"rankings.rankings[{index}]"
        _require(isinstance(run, dict), f"{label} must be an object")
        case_id = _nonempty_string(run.get("case_id"), f"{label}.case_id")
        _require(case_id in case_by_id, f"{label} references unknown case_id {case_id}")
        target = run.get("target")
        _validate_target(case_by_id[case_id], target, run.get("topic_id"), label)
        topic_id = run.get("topic_id") if target == "radar_topic" else None
        retrieval_method = _nonempty_string(run.get("retrieval_method"), f"{label}.retrieval_method")
        key = (case_id, target, topic_id, retrieval_method)
        _require(key not in run_keys, f"Duplicate ranking run key: {key}")
        run_keys.add(key)
        results = run.get("results")
        _require(isinstance(results, list) and len(results) <= MAX_RANKING_ROWS, f"{label}.results must be a list of at most {MAX_RANKING_ROWS} rows")
        seen_ids = set()
        seen_ranks = set()
        clean_results = []
        for result_index, result in enumerate(results):
            result_label = f"{label}.results[{result_index}]"
            _require(isinstance(result, dict), f"{result_label} must be an object")
            arxiv_id = _nonempty_string(result.get("arxiv_id"), f"{result_label}.arxiv_id")
            rank = result.get("rank")
            _require(type(rank) is int and rank >= 1, f"{result_label}.rank must be a positive integer")
            _require(arxiv_id not in seen_ids, f"{label} contains duplicate exact arxiv_id {arxiv_id}")
            _require(rank not in seen_ranks, f"{label} contains duplicate rank {rank}")
            seen_ids.add(arxiv_id)
            seen_ranks.add(rank)
            score = result.get("retrieval_score")
            if score is not None:
                _require(type(score) in {int, float} and math.isfinite(score), f"{result_label}.retrieval_score must be finite numeric or null")
            clean_results.append({"arxiv_id": arxiv_id, "rank": rank, "retrieval_score": score})
        normalized_runs.append({**run, "topic_id": topic_id, "results": sorted(clean_results, key=lambda item: item["rank"])})
    return case_by_id, judgment_by_key, normalized_runs


def _validate_target(case: dict[str, Any], target: Any, topic_id: Any, label: str) -> None:
    _require(isinstance(target, str) and target in TARGETS, f"{label}.target must be one of {sorted(TARGETS)}")
    if case["query_type"] == "project_match":
        _require(target == "project_match", f"{label}.target does not match project_match case")
        _require(topic_id is None, f"{label}.topic_id is only valid for radar_topic")
    else:
        _require(target in {"radar_fused", "radar_topic"}, f"{label}.target does not match research_radar case")
        if target == "radar_topic":
            _nonempty_string(topic_id, f"{label}.topic_id")
            topics = case["query"].get("topics", [])
            _require(topic_id in topics, f"{label}.topic_id must match a topic defined in the case")
        else:
            _require(topic_id is None, f"{label}.topic_id is only valid for radar_topic")


def _dcg(relevances: list[int], cutoff: int) -> float:
    return sum((2**relevance - 1) / math.log2(rank + 1) for rank, relevance in enumerate(relevances[:cutoff], start=1))


def evaluate_run(run: dict[str, Any], judgment_record: dict[str, Any]) -> dict[str, Any]:
    judgments = {item["arxiv_id"]: item["relevance"] for item in judgment_record["judgments"]}
    ranked = run["results"]
    retrieved_ids = [item["arxiv_id"] for item in ranked]
    retrieved_grades = [judgments.get(arxiv_id, 0) for arxiv_id in retrieved_ids]
    relevant_ids = {arxiv_id for arxiv_id, grade in judgments.items() if grade > 0}
    relevant_retrieved = sum(1 for grade in retrieved_grades[:10] if grade > 0)
    judged_count = sum(1 for arxiv_id in retrieved_ids if arxiv_id in judgments)
    total_count = len(retrieved_ids)
    metrics: dict[str, float | None] = {
        "ndcg@5": None,
        "ndcg@10": None,
        "precision@5": sum(grade > 0 for grade in retrieved_grades[:5]) / 5,
        "precision@10": sum(grade > 0 for grade in retrieved_grades[:10]) / 10,
        "recall@10": None,
        "mrr@10": None,
        "judged_result_coverage": judged_count / total_count if total_count else None,
        "unjudged_result_proportion": (total_count - judged_count) / total_count if total_count else None,
    }
    if relevant_ids:
        ideal = sorted(judgments.values(), reverse=True)
        for cutoff in (5, 10):
            denominator = _dcg(ideal, cutoff)
            metrics[f"ndcg@{cutoff}"] = _dcg(retrieved_grades, cutoff) / denominator if denominator else None
        metrics["recall@10"] = relevant_retrieved / len(relevant_ids)
        first_relevant_rank = next(
            (rank for rank, grade in enumerate(retrieved_grades[:10], start=1) if grade > 0), None
        )
        metrics["mrr@10"] = 1 / first_relevant_rank if first_relevant_rank else 0.0
    return {
        "metrics": metrics,
        "counts": {
            "retrieved": total_count,
            "judged_retrieved": judged_count,
            "unjudged_retrieved": total_count - judged_count,
            "judged_relevant_total": len(relevant_ids),
            "relevant_retrieved_at_10": relevant_retrieved,
        },
        "no_relevant_judgments": not relevant_ids,
    }


def _macro_average(rows: list[dict[str, Any]]) -> dict[str, float | None]:
    aggregate = {}
    for key in METRIC_KEYS:
        values = [row["metrics"][key] for row in rows if row.get("metrics") and row["metrics"][key] is not None]
        aggregate[key] = statistics.fmean(values) if values else None
    return aggregate


def evaluate(queries: dict[str, Any], judgments: dict[str, Any], rankings: dict[str, Any]) -> dict[str, Any]:
    case_by_id, judgment_by_key, runs = validate_inputs(queries, judgments, rankings)
    per_query = []
    exclusion_counts = {"missing_judgment_record": 0, "unjudged_annotation": 0, "no_relevant_judgments": 0}
    warnings = []
    for run in runs:
        case_id, target, topic_id = run["case_id"], run["target"], run["topic_id"]
        key = (case_id, target, topic_id)
        judgment_record = judgment_by_key.get(key)
        query_label = f"{case_id}:{target}" + (f":{topic_id}" if topic_id else "")
        row: dict[str, Any] = {
            "case_id": case_id,
            "query_type": case_by_id[case_id]["query_type"],
            "target": target,
            "topic_id": topic_id,
            "retrieval_method": run["retrieval_method"],
            "metadata_snapshot": run.get("metadata_snapshot"),
            "query_label": query_label,
        }
        if judgment_record is None:
            exclusion_counts["missing_judgment_record"] += 1
            row.update({"annotation_status": "missing", "exclusion_reason": "No judgment record for this target", "metrics": None})
        elif judgment_record["annotation_status"] == "unjudged":
            exclusion_counts["unjudged_annotation"] += 1
            row.update({"annotation_status": "unjudged", "exclusion_reason": "Judgment record is explicitly unjudged", "metrics": None})
        else:
            measured = evaluate_run(run, judgment_record)
            row.update({"annotation_status": "judged", **measured})
            if measured["no_relevant_judgments"]:
                exclusion_counts["no_relevant_judgments"] += 1
                warnings.append(f"{query_label}: no positive relevance judgments; nDCG, Recall, and MRR are undefined and excluded from those aggregates.")
            if measured["counts"]["unjudged_retrieved"]:
                warnings.append(
                    f"{query_label}: {measured['counts']['unjudged_retrieved']} of {measured['counts']['retrieved']} retrieved papers are unjudged; metrics use the documented zero-gain convention."
                )
        per_query.append(row)

    evaluated = [row for row in per_query if row.get("metrics") is not None]
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in evaluated:
        groups[(row["retrieval_method"], row["target"])].append(row)
    grouped = [
        {"retrieval_method": method, "target": target, "query_count": len(rows), "metrics": _macro_average(rows)}
        for (method, target), rows in sorted(groups.items())
    ]
    unjudged_results = sum(row.get("counts", {}).get("unjudged_retrieved", 0) for row in evaluated)
    retrieved_results = sum(row.get("counts", {}).get("retrieved", 0) for row in evaluated)
    evaluated_query_count = len(evaluated)
    return {
        "report_version": REPORT_VERSION,
        "benchmark": {"benchmark_id": queries["benchmark_id"], "benchmark_version": queries["benchmark_version"], "format_version": FORMAT_VERSION},
        "evaluation_convention": {
            "ranking_metrics": "Metrics use ranking positions; an unjudged retrieved paper receives zero gain and is explicitly counted/warned about. This is an evaluation convention, not a claim that the paper is irrelevant.",
            "precision": "Precision@k divides relevant retrieved results by the fixed cutoff k, including missing result slots.",
            "ndcg_gain": "2^relevance - 1",
            "ndcg_discount": "log2(rank + 1), with ranks starting at 1",
            "recall_denominator": "All documents with positive judgments in the target's judgment record; judgment completeness is the annotator's responsibility.",
            "no_positive_judgments": "nDCG, Recall, and MRR are null and excluded from their macro averages; Precision remains defined by the fixed-cutoff convention.",
            "raw_scores": "retrieval_score is retained only as snapshot provenance and is never used in metric calculations.",
        },
        "summary": {
            "ranking_run_count": len(runs),
            "evaluated_query_count": evaluated_query_count,
            "excluded_query_count": len(runs) - evaluated_query_count,
            "exclusion_counts": exclusion_counts,
            "retrieved_result_count": retrieved_results,
            "unjudged_retrieved_count": unjudged_results,
            "unjudged_retrieved_proportion": unjudged_results / retrieved_results if retrieved_results else None,
            "average_judged_result_coverage": _macro_average(evaluated).get("judged_result_coverage"),
        },
        "overall_macro_average": _macro_average(evaluated),
        "grouped_macro_averages": grouped,
        "per_query": per_query,
        "data_quality_warnings": warnings,
    }


def render_markdown(report: dict[str, Any]) -> str:
    benchmark = report["benchmark"]
    summary = report["summary"]
    lines = [
        f"# Offline Retrieval Evaluation — {benchmark['benchmark_id']} v{benchmark['benchmark_version']}",
        "",
        f"Benchmark format: `{benchmark['format_version']}` · Report format: `{report['report_version']}`",
        "",
        "## Summary",
        "",
        f"- Ranking runs: {summary['ranking_run_count']}",
        f"- Evaluated targets: {summary['evaluated_query_count']}",
        f"- Excluded targets: {summary['excluded_query_count']} ({json.dumps(summary['exclusion_counts'], sort_keys=True)})",
        f"- Retrieved results: {summary['retrieved_result_count']}; unjudged: {summary['unjudged_retrieved_count']} ({_format_metric(summary['unjudged_retrieved_proportion'])})",
        f"- Average judged-result coverage: {_format_metric(summary['average_judged_result_coverage'])}",
        "",
        "## Overall macro averages",
        "",
        "| Metric | Value |",
        "|---|---:|",
    ]
    for key in sorted(report["overall_macro_average"]):
        lines.append(f"| {key} | {_format_metric(report['overall_macro_average'][key])} |")
    lines.extend(["", "## By retrieval method and target", ""])
    if report["grouped_macro_averages"]:
        lines.extend(["| Method | Target | Queries | nDCG@5 | nDCG@10 | P@5 | P@10 | R@10 | MRR@10 |", "|---|---|---:|---:|---:|---:|---:|---:|---:|"])
        for group in report["grouped_macro_averages"]:
            metrics = group["metrics"]
            lines.append(
                f"| {group['retrieval_method']} | {group['target']} | {group['query_count']} | "
                f"{_format_metric(metrics['ndcg@5'])} | {_format_metric(metrics['ndcg@10'])} | "
                f"{_format_metric(metrics['precision@5'])} | {_format_metric(metrics['precision@10'])} | "
                f"{_format_metric(metrics['recall@10'])} | {_format_metric(metrics['mrr@10'])} |"
            )
    else:
        lines.append("No judged ranking targets were available.")
    lines.extend(["", "## Per-query breakdown", ""])
    if report["per_query"]:
        lines.extend(["| Query target | Method | Status | nDCG@5 | nDCG@10 | P@5 | P@10 | R@10 | MRR@10 | Judged coverage | Unjudged |", "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|"])
        for row in report["per_query"]:
            metrics = row.get("metrics") or {}
            counts = row.get("counts") or {}
            lines.append(
                f"| {row['query_label']} | {row['retrieval_method']} | {row['annotation_status']} | "
                + " | ".join(_format_metric(metrics.get(key)) for key in ("ndcg@5", "ndcg@10", "precision@5", "precision@10", "recall@10", "mrr@10", "judged_result_coverage"))
                + f" | {counts.get('unjudged_retrieved', '—')} |"
            )
    else:
        lines.append("No ranking runs were provided.")
    lines.extend(["", "## Data-quality warnings", ""])
    if report["data_quality_warnings"]:
        lines.extend(f"- {warning}" for warning in report["data_quality_warnings"])
    else:
        lines.append("None.")
    lines.extend(
        [
            "",
            "Unjudged results receive zero gain only as an explicit metric convention; this is not a definitive irrelevance label. Ranking scores are not used in these metrics.",
            "",
        ]
    )
    return "\n".join(lines)


def _format_metric(value: Any) -> str:
    return "—" if value is None else f"{value:.4f}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queries", required=True, help="Versioned query-definition JSON")
    parser.add_argument("--judgments", required=True, help="Versioned relevance-judgment JSON")
    parser.add_argument("--rankings", required=True, help="Frozen ranked-snapshot JSON")
    parser.add_argument("--json-out", required=True, help="Path to machine-readable JSON report")
    parser.add_argument("--markdown-out", required=True, help="Path to Markdown report")
    args = parser.parse_args(argv)
    try:
        report = evaluate(_read_json(args.queries), _read_json(args.judgments), _read_json(args.rankings))
        json_path, markdown_path = Path(args.json_out), Path(args.markdown_out)
        json_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
        markdown_path.write_text(render_markdown(report), encoding="utf-8")
    except EvaluationInputError as exc:
        print(f"evaluation input error: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"report output error: {exc}", file=sys.stderr)
        return 2
    print(f"Wrote JSON report to {json_path}")
    print(f"Wrote Markdown report to {markdown_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
