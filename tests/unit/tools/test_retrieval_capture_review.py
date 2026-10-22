import copy
from io import BytesIO
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tools.capture_retrieval_snapshots import (
    CaptureFailure,
    CaptureInputError,
    build_request,
    capture,
    http_json_post,
    main as capture_main,
    normalize_response,
    validate_base_url,
)
from tools.prepare_relevance_review import (
    ReviewInputError,
    build_packet,
    convert_annotations,
    main as review_main,
)
from tools.retrieval_eval import validate_inputs

QUERY_FILE = Path("benchmarks/ai_ml_research_v1/queries.json")


def queries():
    return json.loads(QUERY_FILE.read_text(encoding="utf-8"))


def response(arxiv_id="2401.00001v2", **overrides):
    paper = {
        "arxiv_id": arxiv_id,
        "retrieval_rank": 1,
        "overall_rank": 1,
        "search_score": 7.2,
        "fusion_score": 0.03,
        "title": "Neural retrieval for research",
        "abstract_excerpt": "A bounded abstract excerpt.",
        "authors": ["A. Researcher"],
        "categories": ["cs.IR", "cs.CL"],
        "published_date": "2025-01-02T00:00:00Z",
        "pdf_url": f"https://arxiv.org/pdf/{arxiv_id}.pdf",
        "source_url": f"https://arxiv.org/abs/{arxiv_id}",
    }
    paper.update(overrides)
    return {"papers": [paper], "result_count": 1}


def test_project_and_radar_payloads_preserve_supported_query_constraints():
    cases = {case["case_id"]: case for case in queries()["cases"]}
    endpoint, project, target, method = build_request(cases["project-efficient-llm-serving-001"])
    assert endpoint == "/api/v1/papers/match-project"
    assert target == "project_match" and method == "project_match_metadata_bm25"
    assert project["project_description"].startswith("Serve transformer")
    assert project["categories"] == ["cs.CL", "cs.LG"]
    assert project["date_from"] == "2022-01-01"
    assert project["top_k"] == 10

    endpoint, radar, target, method = build_request(cases["radar-neural-information-retrieval-001"])
    assert endpoint == "/api/v1/papers/radar"
    assert target == "radar_fused" and method == "research_radar_rrf_k60"
    assert radar["topics"] == ["dense information retrieval", "neural reranking", "retrieval augmented generation"]
    assert radar["lookback_days"] == 30
    assert radar["categories"] == ["cs.IR", "cs.CL"]
    assert radar["top_k"] == 10 and radar["per_topic_candidate_limit"] == 20


def test_unsupported_constraints_and_invalid_base_urls_are_rejected():
    case = copy.deepcopy(queries()["cases"][-1])
    case["expected_filters"]["date_from"] = "2025-01-01"
    with pytest.raises(CaptureInputError, match="Radar accepts lookback_days"):
        build_request(case)
    with pytest.raises(CaptureInputError, match="on or before"):
        build_request({
            "case_id": "bad-date", "query_type": "project_match",
            "query": {"project_description": "valid"},
            "expected_filters": {"date_from": "2025-02-01", "date_to": "2025-01-01"},
        })
    with pytest.raises(CaptureInputError, match="credentials"):
        validate_base_url("https://user:secret@example.org")
    with pytest.raises(CaptureInputError, match="query parameters"):
        validate_base_url("https://example.org?token=secret")


def test_validate_only_builds_payloads_without_transport_or_output_files(tmp_path):
    output_snapshots = tmp_path / "rankings.json"
    output_manifest = tmp_path / "manifest.json"
    called = False

    def forbidden_transport(*args):
        nonlocal called
        called = True
        raise AssertionError("Dry run must not make a request")

    ranking, manifest = capture(
        queries(), "https://example.org/private-prefix", selected_case_ids=["project-rag-literature-assistant-001"],
        dry_run=True, transport=forbidden_transport,
        now=lambda: datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    assert not called
    assert ranking["rankings"] == []
    assert manifest["cases"][0]["status"] == "validated"
    assert manifest["cases"][0]["request_payload"]["categories"] == ["cs.IR", "cs.CL"]
    assert not output_snapshots.exists() and not output_manifest.exists()
    assert manifest["api_origin"] == "https://example.org"
    assert "private-prefix" not in json.dumps(manifest)


def test_normalization_preserves_exact_versioned_ids_and_rejects_duplicate_ids():
    case = queries()["cases"][0]
    run, metadata = normalize_response(case, response(), "project_match", "project_match_metadata_bm25")
    assert run["results"][0]["arxiv_id"] == "2401.00001v2"
    assert run["results"][0]["retrieval_score"] == 7.2
    assert metadata[0]["source_url"] == "https://arxiv.org/abs/2401.00001v2"
    repeated = {"papers": [response()["papers"][0], response()["papers"][0]]}
    with pytest.raises(CaptureFailure, match="duplicate_arxiv_id"):
        normalize_response(case, repeated, "project_match", "project_match_metadata_bm25")
    older_version = response("2401.00001v1")["papers"][0]
    older_version["retrieval_rank"] = 2
    distinct_versions = {"papers": [response()["papers"][0], older_version]}
    run, _ = normalize_response(case, distinct_versions, "project_match", "project_match_metadata_bm25")
    assert [row["arxiv_id"] for row in run["results"]] == ["2401.00001v2", "2401.00001v1"]


def test_empty_result_is_success_but_http_error_and_timeout_are_manifest_failures():
    query_file = queries()
    case_ids = ["project-rag-literature-assistant-001"]
    empty_rankings, empty_manifest = capture(
        query_file, "https://example.org", selected_case_ids=case_ids,
        transport=lambda *args: (200, {"papers": [], "result_count": 0}),
    )
    assert len(empty_rankings["rankings"]) == 1
    assert empty_rankings["rankings"][0]["results"] == []
    assert empty_manifest["cases"][0]["status"] == "success"

    failed_rankings, failed_manifest = capture(
        query_file, "https://example.org", selected_case_ids=case_ids,
        transport=lambda *args: (_ for _ in ()).throw(CaptureFailure("http_error", 503)),
    )
    assert failed_rankings["rankings"] == []
    assert failed_manifest["cases"][0]["http_status"] == 503
    assert failed_manifest["cases"][0]["error_category"] == "http_error"
    timed = capture(
        query_file, "https://example.org", selected_case_ids=case_ids,
        transport=lambda *args: (_ for _ in ()).throw(CaptureFailure("timeout")),
    )[1]["cases"][0]
    assert timed["error_category"] == "timeout" and timed["attempts"] == 1


def test_http_transport_translates_errors_without_exposing_response_details(monkeypatch):
    import tools.capture_retrieval_snapshots as capture_module
    from urllib.error import HTTPError

    def http_error(*args, **kwargs):
        raise HTTPError("https://example.org/api", 503, "secret backend detail", {}, BytesIO(b"secret body"))

    monkeypatch.setattr(capture_module, "urlopen", http_error)
    with pytest.raises(CaptureFailure) as error:
        http_json_post("https://example.org/api", {"query": "safe"}, 2)
    assert error.value.category == "http_error"
    assert error.value.http_status == 503
    assert "secret" not in str(error.value)

    def timeout(*args, **kwargs):
        raise TimeoutError("private token detail")

    monkeypatch.setattr(capture_module, "urlopen", timeout)
    with pytest.raises(CaptureFailure) as error:
        http_json_post("https://example.org/api", {"query": "safe"}, 2)
    assert error.value.category == "timeout"
    assert "private" not in str(error.value)


def test_capture_retries_are_limited_and_manifest_has_sanitized_provenance():
    attempts = []

    def transient_once(url, payload, timeout):
        attempts.append(url)
        if len(attempts) == 1:
            raise CaptureFailure("http_error", 503)
        return 200, response()

    rankings, manifest = capture(
        queries(), "https://example.org/deployment", selected_case_ids=["project-rag-literature-assistant-001"],
        retries=1, transport=transient_once,
        now=lambda: datetime(2026, 2, 3, 4, 5, 6, tzinfo=timezone.utc),
    )
    assert len(attempts) == 2
    assert rankings["rankings"][0]["case_id"] == "project-rag-literature-assistant-001"
    assert manifest["captured_at_utc"] == "2026-02-03T04:05:06Z"
    assert manifest["metadata_snapshot"] is None
    assert manifest["cases"][0]["attempts"] == 2
    assert manifest["api_origin"] == "https://example.org"
    serialized = json.dumps(manifest)
    assert "Authorization" not in serialized and "token=" not in serialized
    judgment_header = {
        "format_version": "1.0",
        "benchmark_id": rankings["benchmark_id"],
        "benchmark_version": rankings["benchmark_version"],
        "cases": [],
    }
    validate_inputs(queries(), judgment_header, rankings)


def test_packet_separates_source_metadata_and_unjudged_annotations_and_converts():
    query_doc = {"format_version": "1.0", "benchmark_id": "b", "benchmark_version": "1", "cases": [
        {"case_id": "case-1", "query_type": "project_match", "query": {"project_description": "Find neural retrieval research"}, "expected_filters": {"categories": ["cs.IR"]}}
    ]}
    ranking_doc = {"format_version": "1.0", "benchmark_id": "b", "benchmark_version": "1", "rankings": [
        {"case_id": "case-1", "target": "project_match", "retrieval_method": "bm25", "results": [{"arxiv_id": "2401.00001v2", "rank": 1}]}
    ]}
    manifest_doc = {"capture_format_version": "1.0", "benchmark_id": "b", "benchmark_version": "1", "captured_at_utc": "2026-02-03T04:05:06Z", "cases": [
        {"case_id": "case-1", "status": "success", "paper_metadata": [{"arxiv_id": "2401.00001v2", "rank": 1, "title": "Neural retrieval", "abstract": "Abstract", "authors": ["A"], "categories": ["cs.IR"], "published_date": "2025-01-01", "source_url": "https://arxiv.org/abs/2401.00001v2"}]}
    ]}
    packet, annotations = build_packet(query_doc, ranking_doc, manifest_doc)
    review_case = packet["cases"][0]
    assert review_case["papers"][0]["title"] == "Neural retrieval"
    annotation_case = annotations["cases"][0]
    assert annotation_case["papers"][0]["annotation_status"] == "unjudged"
    assert annotation_case["papers"][0]["relevance"] is None

    annotation_case["papers"][0].update({
        "annotation_status": "judged", "relevance": 3,
        "rationale": "Directly studies neural retrieval for the stated project.",
        "reviewer_id": "reviewer-01", "annotated_at": "2026-02-04",
    })
    converted = convert_annotations(packet, annotations)
    assert converted["cases"][0]["annotation_status"] == "judged"
    assert converted["cases"][0]["judgments"][0]["arxiv_id"] == "2401.00001v2"
    validate_inputs(query_doc, converted, ranking_doc)
    incomplete = copy.deepcopy(annotations)
    incomplete["cases"][0]["papers"] = []
    with pytest.raises(ReviewInputError, match="retain every exact paper ID"):
        convert_annotations(packet, incomplete)


def test_human_annotation_validation_and_packet_output_overwrite_protection(tmp_path):
    query_doc = {"format_version": "1.0", "benchmark_id": "b", "benchmark_version": "1", "cases": [
        {"case_id": "case-1", "query_type": "project_match", "query": {"project_description": "query"}}
    ]}
    ranking_doc = {"format_version": "1.0", "benchmark_id": "b", "benchmark_version": "1", "rankings": [
        {"case_id": "case-1", "target": "project_match", "retrieval_method": "bm25", "results": [{"arxiv_id": "id.v1", "rank": 1}]}
    ]}
    manifest_doc = {"capture_format_version": "1.0", "benchmark_id": "b", "benchmark_version": "1", "cases": [
        {"case_id": "case-1", "status": "success", "paper_metadata": [{"arxiv_id": "id.v1", "rank": 1}]}
    ]}
    packet, annotations = build_packet(query_doc, ranking_doc, manifest_doc)
    annotations["cases"][0]["papers"][0].update({"annotation_status": "judged", "relevance": 4, "rationale": "bad"})
    with pytest.raises(ReviewInputError, match="0 to 3"):
        convert_annotations(packet, annotations)

    query_path = tmp_path / "queries.json"
    snapshot_path = tmp_path / "snapshots.json"
    manifest_path = tmp_path / "manifest.json"
    query_path.write_text(json.dumps(query_doc), encoding="utf-8")
    snapshot_path.write_text(json.dumps(ranking_doc), encoding="utf-8")
    manifest_path.write_text(json.dumps(manifest_doc), encoding="utf-8")
    packet_path = tmp_path / "review.json"
    annotation_path = tmp_path / "annotations.json"
    packet_path.write_text("preserve", encoding="utf-8")
    exit_code = review_main([
        "packet", "--queries", str(query_path), "--snapshots", str(snapshot_path), "--manifest", str(manifest_path),
        "--packet-out", str(packet_path), "--annotations-out", str(annotation_path),
    ])
    assert exit_code == 2
    assert packet_path.read_text(encoding="utf-8") == "preserve"
    assert not annotation_path.exists()


def test_capture_cli_refuses_to_overwrite_and_dry_run_is_offline(tmp_path):
    query_path = QUERY_FILE
    snapshot_path = tmp_path / "rankings.json"
    manifest_path = tmp_path / "manifest.json"
    snapshot_path.write_text("keep", encoding="utf-8")
    result = capture_main([
        "--queries", str(query_path), "--api-base-url", "https://example.org",
        "--snapshots-out", str(snapshot_path), "--manifest-out", str(manifest_path),
    ])
    assert result == 2
    assert snapshot_path.read_text(encoding="utf-8") == "keep"

    result = capture_main([
        "--queries", str(query_path), "--api-base-url", "https://example.org",
        "--snapshots-out", str(snapshot_path), "--manifest-out", str(manifest_path),
        "--validate-only", "--case-id", "project-rag-literature-assistant-001",
    ])
    assert result == 0
