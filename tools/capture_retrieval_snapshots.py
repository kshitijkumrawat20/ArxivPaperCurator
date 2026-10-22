#!/usr/bin/env python3
"""Explicitly capture frozen Project Match or Research Radar API rankings.

This tool is never invoked by the application, tests, or ingestion schedule.
Network access occurs only when a human explicitly runs capture mode.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen

FORMAT_VERSION = "1.0"
DEFAULT_TIMEOUT = 10.0
MAX_TIMEOUT = 30.0


class CaptureInputError(ValueError):
    pass


class CaptureFailure(Exception):
    def __init__(self, category: str, http_status: int | None = None):
        super().__init__(category)
        self.category = category
        self.http_status = http_status


def _read_json(path: str | Path) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CaptureInputError(f"Could not read benchmark JSON: {type(exc).__name__}") from exc
    if not isinstance(value, dict):
        raise CaptureInputError("Benchmark JSON must be an object")
    return value


def validate_base_url(value: str) -> str:
    try:
        parts = urlsplit(value)
        _ = parts.port  # validates malformed ports
    except ValueError as exc:
        raise CaptureInputError("API base URL is malformed") from exc
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise CaptureInputError("API base URL must use http or https and include a host")
    if parts.username or parts.password or parts.query or parts.fragment:
        raise CaptureInputError("API base URL must not contain credentials, query parameters, or a fragment")
    return value.rstrip("/")


def _validate_query_file(queries: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if queries.get("format_version") != FORMAT_VERSION:
        raise CaptureInputError(f"Query format_version must be {FORMAT_VERSION}")
    if not isinstance(queries.get("benchmark_id"), str) or not queries["benchmark_id"].strip():
        raise CaptureInputError("benchmark_id must be a non-empty string")
    if not isinstance(queries.get("benchmark_version"), str) or not queries["benchmark_version"].strip():
        raise CaptureInputError("benchmark_version must be a non-empty string")
    cases = queries.get("cases")
    if not isinstance(cases, list) or not cases:
        raise CaptureInputError("cases must be a non-empty list")
    result = {}
    for case in cases:
        if not isinstance(case, dict):
            raise CaptureInputError("Every case must be an object")
        case_id = case.get("case_id")
        if not isinstance(case_id, str) or not case_id.strip() or case_id in result:
            raise CaptureInputError("case_id values must be non-empty and unique")
        query_type = case.get("query_type")
        query = case.get("query")
        filters = case.get("expected_filters", {})
        if not isinstance(query_type, str) or query_type not in {"project_match", "research_radar"} or not isinstance(query, dict):
            raise CaptureInputError(f"Case {case_id} has an unsupported query_type or invalid query")
        if not isinstance(filters, dict):
            raise CaptureInputError(f"Case {case_id} expected_filters must be an object")
        if set(filters) - {"categories", "date_from", "date_to"}:
            raise CaptureInputError(f"Case {case_id} has unsupported expected_filters")
        result[case_id] = case
    return result


def build_request(case: dict[str, Any]) -> tuple[str, dict[str, Any], str, str]:
    """Return endpoint path, schema-valid payload, evaluator target and method label."""
    query = case["query"]
    filters = case.get("expected_filters", {})
    categories = filters.get("categories", [])
    if not isinstance(categories, list) or any(not isinstance(category, str) for category in categories):
        raise CaptureInputError(f"Case {case['case_id']} categories must be a list of strings")
    if len(categories) > 20:
        raise CaptureInputError(f"Case {case['case_id']} may specify at most 20 categories")
    if any(not re.fullmatch(r"[A-Za-z][A-Za-z0-9.-]{1,31}", category) for category in categories):
        raise CaptureInputError(f"Case {case['case_id']} contains an invalid arXiv category")

    if case["query_type"] == "project_match":
        allowed = {"project_title", "project_description", "technologies", "research_interests", "top_k"}
        unknown = set(query) - allowed
        if unknown:
            raise CaptureInputError(f"Case {case['case_id']} has unsupported Project Match query fields")
        if not isinstance(query.get("project_description"), str) or not query["project_description"].strip():
            raise CaptureInputError(f"Case {case['case_id']} requires project_description")
        payload = {key: query[key] for key in ("project_description", "project_title", "technologies", "research_interests", "top_k") if key in query}
        if len(payload["project_description"]) > 2000:
            raise CaptureInputError(f"Case {case['case_id']} project_description exceeds 2000 characters")
        if "project_title" in payload and (not isinstance(payload["project_title"], str) or len(payload["project_title"]) > 200):
            raise CaptureInputError(f"Case {case['case_id']} project_title must be at most 200 characters")
        for field in ("technologies", "research_interests"):
            values = payload.get(field, [])
            if not isinstance(values, list) or len(values) > 20 or any(
                not isinstance(value, str) or not value.strip() or len(value) > 100 for value in values
            ):
                raise CaptureInputError(f"Case {case['case_id']} {field} must contain at most 20 non-empty terms of at most 100 characters")
        payload["categories"] = categories
        parsed_dates = {}
        for field in ("date_from", "date_to"):
            value = filters.get(field)
            if value is not None:
                if not isinstance(value, str):
                    raise CaptureInputError(f"Case {case['case_id']} {field} must be an ISO date")
                try:
                    parsed_dates[field] = date.fromisoformat(value)
                except ValueError as exc:
                    raise CaptureInputError(f"Case {case['case_id']} {field} must be an ISO date") from exc
                payload[field] = value
        if "date_from" in parsed_dates and "date_to" in parsed_dates and parsed_dates["date_from"] > parsed_dates["date_to"]:
            raise CaptureInputError(f"Case {case['case_id']} date_from must be on or before date_to")
        _validate_limit(payload, "top_k", 1, 20, 10, case["case_id"])
        return "/api/v1/papers/match-project", payload, "project_match", "project_match_metadata_bm25"

    allowed = {"topics", "lookback_days", "top_k", "per_topic_candidate_limit"}
    unknown = set(query) - allowed
    if unknown:
        raise CaptureInputError(f"Case {case['case_id']} has unsupported Research Radar query fields")
    topics = query.get("topics")
    if not isinstance(topics, list) or not 1 <= len(topics) <= 8 or any(not isinstance(topic, str) or not topic.strip() for topic in topics):
        raise CaptureInputError(f"Case {case['case_id']} requires 1-8 non-empty radar topics")
    normalized_topics = []
    seen_topics = set()
    for topic in topics:
        normalized = " ".join(topic.split())
        if len(normalized) > 120:
            raise CaptureInputError(f"Case {case['case_id']} radar topics must be at most 120 characters")
        if normalized.casefold() not in seen_topics:
            normalized_topics.append(normalized)
            seen_topics.add(normalized.casefold())
    if not normalized_topics or sum(map(len, normalized_topics)) + len(normalized_topics) - 1 > 500:
        raise CaptureInputError(f"Case {case['case_id']} normalized radar topics must total at most 500 characters")
    for field in ("date_from", "date_to"):
        if filters.get(field) is not None:
            raise CaptureInputError(f"Case {case['case_id']} has explicit {field}; Radar accepts lookback_days, not date bounds")
    payload = {key: query[key] for key in ("topics", "lookback_days", "top_k", "per_topic_candidate_limit") if key in query}
    payload["topics"] = normalized_topics
    payload["categories"] = categories
    _validate_limit(payload, "lookback_days", 1, 365, 30, case["case_id"])
    _validate_limit(payload, "top_k", 1, 20, 10, case["case_id"])
    _validate_limit(payload, "per_topic_candidate_limit", 1, 50, 20, case["case_id"])
    return "/api/v1/papers/radar", payload, "radar_fused", "research_radar_rrf_k60"


def _validate_limit(payload: dict[str, Any], field: str, lower: int, upper: int, default: int, case_id: str) -> None:
    value = payload.get(field, default)
    if type(value) is not int or not lower <= value <= upper:
        raise CaptureInputError(f"Case {case_id} {field} must be an integer from {lower} to {upper}")
    payload[field] = value


def _append_url(base_url: str, endpoint: str) -> str:
    return f"{base_url.rstrip('/')}/{endpoint.lstrip('/')}"


def _origin_only(base_url: str) -> str:
    parts = urlsplit(base_url)
    host = parts.hostname or ""
    if parts.port:
        host = f"{host}:{parts.port}"
    return urlunsplit((parts.scheme, host, "", "", ""))


def http_json_post(url: str, payload: dict[str, Any], timeout: float) -> tuple[int, dict[str, Any]]:
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            status = response.status
            body = response.read()
    except HTTPError as exc:
        raise CaptureFailure("http_error", exc.code) from None
    except URLError as exc:
        reason = getattr(exc, "reason", None)
        category = "timeout" if isinstance(reason, TimeoutError) or "timed out" in str(reason).casefold() else "connection_error"
        raise CaptureFailure(category) from None
    except (TimeoutError, OSError) as exc:
        category = "timeout" if isinstance(exc, TimeoutError) or "timed out" in str(exc).casefold() else "connection_error"
        raise CaptureFailure(category) from None
    if not 200 <= status < 300:
        raise CaptureFailure("http_error", status)
    try:
        result = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise CaptureFailure("invalid_json", status) from None
    if not isinstance(result, dict):
        raise CaptureFailure("invalid_response", status)
    return status, result


def normalize_response(
    case: dict[str, Any], response: dict[str, Any], target: str, retrieval_method: str
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    papers = response.get("papers")
    if not isinstance(papers, list):
        raise CaptureFailure("invalid_response")
    result_count = response.get("result_count")
    if result_count is not None and (type(result_count) is not int or result_count != len(papers)):
        raise CaptureFailure("invalid_response")
    results = []
    metadata = []
    seen_ids = set()
    seen_ranks = set()
    rank_field = "retrieval_rank" if target == "project_match" else "overall_rank"
    score_field = "search_score" if target == "project_match" else "fusion_score"
    for position, paper in enumerate(papers, start=1):
        if not isinstance(paper, dict):
            raise CaptureFailure("invalid_response")
        arxiv_id = paper.get("arxiv_id")
        if not isinstance(arxiv_id, str) or not arxiv_id.strip() or arxiv_id != arxiv_id.strip():
            raise CaptureFailure("invalid_response")
        if arxiv_id in seen_ids:
            raise CaptureFailure("duplicate_arxiv_id")
        rank = paper.get(rank_field, position)
        if type(rank) is not int or rank < 1 or rank in seen_ranks:
            raise CaptureFailure("invalid_response")
        score = paper.get(score_field)
        if score is not None and (type(score) not in {int, float} or not math.isfinite(score)):
            raise CaptureFailure("invalid_response")
        authors = paper.get("authors") or []
        categories = paper.get("categories") or []
        if not isinstance(authors, list) or not isinstance(categories, list):
            raise CaptureFailure("invalid_response")
        seen_ids.add(arxiv_id)
        seen_ranks.add(rank)
        results.append({"arxiv_id": arxiv_id, "rank": rank, "retrieval_score": score})
        metadata.append(
            {
                "arxiv_id": arxiv_id,
                "rank": rank,
                "title": str(paper.get("title") or "")[:500],
                "abstract": str(paper.get("abstract_excerpt") or "")[:1000],
                "authors": [str(author)[:200] for author in authors[:50]],
                "categories": [str(category)[:32] for category in categories[:50]],
                "published_date": str(paper.get("published_date") or "")[:40],
                "source_url": str(paper.get("source_url") or paper.get("pdf_url") or "")[:500] or None,
            }
        )
    results.sort(key=lambda row: row["rank"])
    metadata.sort(key=lambda row: row["rank"])
    return (
        {
            "case_id": case["case_id"],
            "query_type": case["query_type"],
            "target": target,
            "retrieval_method": retrieval_method,
            "results": results,
        },
        metadata,
    )


def capture(
    queries: dict[str, Any],
    api_base_url: str,
    *,
    selected_case_ids: list[str] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    retries: int = 0,
    dry_run: bool = False,
    transport: Callable[[str, dict[str, Any], float], dict[str, Any]] = http_json_post,
    now: Callable[[], datetime] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    base_url = validate_base_url(api_base_url)
    if not 1 <= timeout <= MAX_TIMEOUT:
        raise CaptureInputError(f"timeout must be between 1 and {MAX_TIMEOUT} seconds")
    if retries not in {0, 1}:
        raise CaptureInputError("retries must be 0 or 1")
    cases = _validate_query_file(queries)
    selected = selected_case_ids or list(cases)
    unknown = [case_id for case_id in selected if case_id not in cases]
    if unknown:
        raise CaptureInputError("Unknown case_id selection")
    if len(set(selected)) != len(selected):
        raise CaptureInputError("case_id selection contains duplicates")

    timestamp = (now or (lambda: datetime.now(timezone.utc)))().astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    ranking_rows = []
    manifest_rows = []
    for case_id in selected:
        case = cases[case_id]
        endpoint, payload, target, method = build_request(case)
        if dry_run:
            manifest_rows.append({
                "case_id": case_id,
                "query_type": case["query_type"],
                "target": target,
                "retrieval_method": method,
                "status": "validated",
                "endpoint_path": endpoint,
                "request_payload": payload,
            })
            continue
        url = _append_url(base_url, endpoint)
        attempts = 0
        while True:
            attempts += 1
            response_status = None
            try:
                transport_result = transport(url, payload, timeout)
                if isinstance(transport_result, tuple) and len(transport_result) == 2:
                    response_status, response = transport_result
                else:
                    response_status, response = 200, transport_result
                if type(response_status) is not int or not 200 <= response_status < 300:
                    raise CaptureFailure("http_error", response_status if type(response_status) is int else None)
                ranking_row, paper_metadata = normalize_response(case, response, target, method)
                ranking_rows.append(ranking_row)
                manifest_rows.append({
                    "case_id": case_id,
                    "query_type": case["query_type"],
                    "target": target,
                    "retrieval_method": method,
                    "status": "success",
                    "endpoint_path": endpoint,
                    "http_status": response_status,
                    "attempts": attempts,
                    "result_count": len(ranking_row["results"]),
                    "paper_metadata": paper_metadata,
                })
                break
            except CaptureFailure as exc:
                retryable = exc.category in {"timeout", "connection_error"} or (
                    exc.category == "http_error" and exc.http_status in {429, 500, 502, 503, 504}
                )
                if attempts <= retries and retryable:
                    continue
                manifest_rows.append({
                    "case_id": case_id,
                    "query_type": case["query_type"],
                    "target": target,
                    "retrieval_method": method,
                    "status": "failed",
                    "endpoint_path": endpoint,
                    "http_status": exc.http_status or response_status,
                    "attempts": attempts,
                    "error_category": exc.category,
                })
                break
            except (TimeoutError, OSError):
                exception = sys.exc_info()[1]
                category = "timeout" if isinstance(exception, TimeoutError) or "timed out" in str(exception).casefold() else "connection_error"
                if attempts <= retries:
                    continue
                manifest_rows.append({
                    "case_id": case_id,
                    "query_type": case["query_type"],
                    "target": target,
                    "retrieval_method": method,
                    "status": "failed",
                    "endpoint_path": endpoint,
                    "http_status": None,
                    "attempts": attempts,
                    "error_category": category,
                })
                break
            except Exception:
                manifest_rows.append({
                    "case_id": case_id,
                    "query_type": case["query_type"],
                    "target": target,
                    "retrieval_method": method,
                    "status": "failed",
                    "endpoint_path": endpoint,
                    "http_status": response_status,
                    "attempts": attempts,
                    "error_category": "invalid_response",
                })
                break

    ranking_artifact = {
        "format_version": FORMAT_VERSION,
        "benchmark_id": queries["benchmark_id"],
        "benchmark_version": queries["benchmark_version"],
        "rankings": ranking_rows,
    }
    manifest = {
        "capture_format_version": FORMAT_VERSION,
        "benchmark_id": queries["benchmark_id"],
        "benchmark_version": queries["benchmark_version"],
        "captured_at_utc": timestamp,
        "api_origin": _origin_only(base_url),
        "metadata_snapshot": None,
        "metadata_snapshot_note": "The endpoint does not expose an index snapshot identifier; capture time is recorded but does not freeze the underlying index.",
        "cases": manifest_rows,
    }
    return ranking_artifact, manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queries", required=True)
    parser.add_argument("--api-base-url", required=True, help="Explicit API origin or deployment prefix; credentials/query strings are rejected")
    parser.add_argument("--snapshots-out", required=True)
    parser.add_argument("--manifest-out", required=True)
    parser.add_argument("--timeout-seconds", type=float, default=DEFAULT_TIMEOUT)
    parser.add_argument("--retries", type=int, choices=(0, 1), default=0)
    parser.add_argument("--case-id", action="append", dest="case_ids", help="Select a case; repeat to select several")
    parser.add_argument("--validate-only", action="store_true", help="Validate payload construction without network or output files")
    parser.add_argument("--overwrite", action="store_true", help="Explicitly allow replacing either output file")
    args = parser.parse_args(argv)
    try:
        queries = _read_json(args.queries)
        cases = _validate_query_file(queries)
        if not args.validate_only:
            snapshots_path, manifest_path = Path(args.snapshots_out), Path(args.manifest_out)
            if snapshots_path.resolve() == manifest_path.resolve():
                raise CaptureInputError("Snapshot and manifest outputs must use different paths")
            if snapshots_path.resolve() == Path(args.queries).resolve() or manifest_path.resolve() == Path(args.queries).resolve():
                raise CaptureInputError("Output paths cannot replace the benchmark query file")
            existing = [path for path in (snapshots_path, manifest_path) if path.exists()]
            if existing and not args.overwrite:
                raise CaptureInputError("Output exists; choose new names or pass --overwrite explicitly")
        rankings, manifest = capture(
            queries,
            args.api_base_url,
            selected_case_ids=args.case_ids,
            timeout=args.timeout_seconds,
            retries=args.retries,
            dry_run=args.validate_only,
        )
        if args.validate_only:
            print(json.dumps({"validated_cases": manifest["cases"]}, indent=2, sort_keys=True))
            return 0
        snapshots_path, manifest_path = Path(args.snapshots_out), Path(args.manifest_out)
        snapshots_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        snapshots_path.write_text(json.dumps(rankings, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    except CaptureInputError as exc:
        print(f"capture input error: {exc}", file=sys.stderr)
        return 2
    print(f"Wrote ranked snapshot artifact to {args.snapshots_out}")
    print(f"Wrote separate capture manifest to {args.manifest_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
