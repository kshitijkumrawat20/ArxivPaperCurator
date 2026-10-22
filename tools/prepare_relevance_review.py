#!/usr/bin/env python3
"""Create source-metadata review packets and convert human annotations."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any

FORMAT_VERSION = "1.0"
SCALE = {
    0: "Not relevant to the stated query",
    1: "Marginally relevant",
    2: "Relevant",
    3: "Highly relevant",
}


class ReviewInputError(ValueError):
    pass


def _read(path: str | Path) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReviewInputError(f"Could not read JSON input: {type(exc).__name__}") from exc
    if not isinstance(value, dict):
        raise ReviewInputError("JSON input must be an object")
    return value


def _write_new(path: str | Path, value: dict[str, Any], overwrite: bool) -> None:
    target = Path(path)
    if target.exists() and not overwrite:
        raise ReviewInputError("Output exists; choose a new path or pass --overwrite explicitly")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def build_packet(queries: dict[str, Any], snapshots: dict[str, Any], manifest: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    identity = (queries.get("format_version"), queries.get("benchmark_id"), queries.get("benchmark_version"))
    if identity[0] != FORMAT_VERSION or not all(isinstance(value, str) and value for value in identity[1:]):
        raise ReviewInputError("Invalid or unsupported query benchmark header")
    for label, artifact in (("snapshots", snapshots), ("manifest", manifest)):
        if (artifact.get("format_version"), artifact.get("benchmark_id"), artifact.get("benchmark_version")) != identity and not (
            label == "manifest"
            and (artifact.get("capture_format_version"), artifact.get("benchmark_id"), artifact.get("benchmark_version")) == identity
        ):
            raise ReviewInputError(f"{label} benchmark identity does not match query file")
    case_by_id = {}
    for case in queries.get("cases", []):
        if not isinstance(case, dict) or not isinstance(case.get("case_id"), str) or case["case_id"] in case_by_id:
            raise ReviewInputError("Query cases must have unique case_id strings")
        case_by_id[case["case_id"]] = case
    manifest_rows = manifest.get("cases")
    if not isinstance(manifest_rows, list):
        raise ReviewInputError("Capture manifest cases must be a list")
    manifest_by_id = {}
    for row in manifest_rows:
        if isinstance(row, dict) and isinstance(row.get("case_id"), str):
            if row["case_id"] in manifest_by_id:
                raise ReviewInputError("Capture manifest contains duplicate case_id entries")
            manifest_by_id[row["case_id"]] = row
    packet_cases, annotation_cases = [], []
    seen_targets = set()
    ranking_rows = snapshots.get("rankings")
    if not isinstance(ranking_rows, list):
        raise ReviewInputError("Snapshot rankings must be a list")
    if not ranking_rows:
        raise ReviewInputError("No successful ranking snapshots are available for review")
    for run in ranking_rows:
        if not isinstance(run, dict):
            raise ReviewInputError("Every snapshot ranking must be an object")
        case_id = run.get("case_id")
        target = run.get("target")
        if not isinstance(case_id, str) or case_id not in case_by_id or not isinstance(target, str) or target not in {"project_match", "radar_fused"}:
            raise ReviewInputError("Snapshot references an unsupported case or target")
        if (case_id, target) in seen_targets:
            raise ReviewInputError("Duplicate case/target ranking snapshot")
        seen_targets.add((case_id, target))
        case_manifest = manifest_by_id.get(case_id)
        if not case_manifest or case_manifest.get("status") != "success":
            raise ReviewInputError(f"Snapshot for {case_id} is not marked successful in capture manifest")
        captured_metadata = case_manifest.get("paper_metadata")
        if not isinstance(captured_metadata, list):
            raise ReviewInputError(f"Successful manifest case {case_id} has no captured paper metadata")
        results = run.get("results")
        if not isinstance(results, list) or any(not isinstance(result, dict) for result in results):
            raise ReviewInputError(f"Snapshot results for {case_id} must be a list of objects")
        if any(not isinstance(paper, dict) for paper in captured_metadata):
            raise ReviewInputError(f"Captured metadata for {case_id} must contain objects")
        result_ids = [result.get("arxiv_id") for result in results]
        metadata_ids = [paper.get("arxiv_id") for paper in captured_metadata]
        if any(not isinstance(arxiv_id, str) or not arxiv_id.strip() for arxiv_id in result_ids + metadata_ids):
            raise ReviewInputError(f"Snapshot and manifest IDs for {case_id} must be non-empty strings")
        if len(set(result_ids)) != len(result_ids) or len(set(metadata_ids)) != len(metadata_ids):
            raise ReviewInputError(f"Duplicate exact arXiv IDs found for {case_id}")
        ranks = [result.get("rank") for result in results]
        if any(type(rank) is not int or rank < 1 for rank in ranks) or len(set(ranks)) != len(ranks):
            raise ReviewInputError(f"Snapshot ranks for {case_id} must be unique positive integers")
        if result_ids != metadata_ids:
            raise ReviewInputError(f"Snapshot and manifest paper IDs/order differ for {case_id}")
        query_case = case_by_id[case_id]
        metadata_by_id = {paper["arxiv_id"]: paper for paper in captured_metadata}
        packet_papers = []
        for result in results:
            arxiv_id = result["arxiv_id"]
            paper = metadata_by_id[arxiv_id]
            packet_papers.append(
                {
                    "arxiv_id": arxiv_id,
                    "rank": result["rank"],
                    "title": paper.get("title", ""),
                    "abstract": paper.get("abstract", ""),
                    "authors": paper.get("authors", []),
                    "categories": paper.get("categories", []),
                    "published_date": paper.get("published_date", ""),
                    "source_url": paper.get("source_url"),
                }
            )
        packet_case = {
            "case_id": case_id,
            "query_type": query_case["query_type"],
            "target": target,
            "query": query_case.get("query", {}),
            "expected_filters": query_case.get("expected_filters", {}),
            "captured_at_utc": manifest.get("captured_at_utc"),
            "papers": packet_papers,
        }
        packet_cases.append(packet_case)
        annotation_cases.append(
            {
                "case_id": case_id,
                "target": target,
                "papers": [
                    {
                        "arxiv_id": paper["arxiv_id"],
                        "annotation_status": "unjudged",
                        "relevance": None,
                        "rationale": "",
                        "reviewer_id": None,
                        "annotated_at": None,
                    }
                    for paper in packet_papers
                ],
            }
        )
    packet = {
        "packet_format_version": FORMAT_VERSION,
        "benchmark_id": identity[1],
        "benchmark_version": identity[2],
        "scale": SCALE,
        "instruction": "Judge each paper against the full project description or research topic, not merely shared keywords. Do not infer relevance from rank alone.",
        "cases": packet_cases,
    }
    annotations = {
        "annotation_format_version": FORMAT_VERSION,
        "benchmark_id": identity[1],
        "benchmark_version": identity[2],
        "cases": annotation_cases,
    }
    return packet, annotations


def convert_annotations(packet: dict[str, Any], annotations: dict[str, Any]) -> dict[str, Any]:
    identity = (packet.get("packet_format_version"), packet.get("benchmark_id"), packet.get("benchmark_version"))
    if identity[0] != FORMAT_VERSION or (
        annotations.get("annotation_format_version"), annotations.get("benchmark_id"), annotations.get("benchmark_version")
    ) != identity:
        raise ReviewInputError("Annotation and review packet versions/identities do not match")
    packet_keys = {}
    for case in packet.get("cases", []):
        key = (case.get("case_id"), case.get("target"))
        if key in packet_keys:
            raise ReviewInputError("Review packet contains duplicate case/target records")
        packet_keys[key] = {paper["arxiv_id"] for paper in case.get("papers", [])}
    annotation_rows = annotations.get("cases")
    if not isinstance(annotation_rows, list):
        raise ReviewInputError("annotations.cases must be a list")
    evaluator_cases = []
    provenance_reviewers = set()
    provenance_dates = set()
    seen_keys = set()
    for row in annotation_rows:
        if not isinstance(row, dict):
            raise ReviewInputError("Every annotation case must be an object")
        case_id, target = row.get("case_id"), row.get("target")
        if not isinstance(case_id, str) or not isinstance(target, str):
            raise ReviewInputError("Annotation case_id and target must be strings")
        key = (case_id, target)
        if key not in packet_keys or key in seen_keys:
            raise ReviewInputError("Annotations must reference each packet case/target at most once")
        seen_keys.add(key)
        papers = row.get("papers")
        if not isinstance(papers, list):
            raise ReviewInputError("Annotation papers must be a list")
        seen_ids = set()
        judgments = []
        for paper in papers:
            if not isinstance(paper, dict):
                raise ReviewInputError("Each paper annotation must be an object")
            arxiv_id = paper.get("arxiv_id")
            if not isinstance(arxiv_id, str) or arxiv_id not in packet_keys[key] or arxiv_id in seen_ids:
                raise ReviewInputError("Annotation IDs must be unique exact IDs from the packet")
            seen_ids.add(arxiv_id)
            status = paper.get("annotation_status")
            if not isinstance(status, str) or status not in {"unjudged", "judged"}:
                raise ReviewInputError("Each annotation status must be unjudged or judged")
            relevance = paper.get("relevance")
            rationale = paper.get("rationale", "")
            reviewer_id = paper.get("reviewer_id")
            annotated_at = paper.get("annotated_at")
            if status == "unjudged":
                if relevance is not None or rationale:
                    raise ReviewInputError("Unjudged papers cannot contain relevance or rationale")
                continue
            if type(relevance) is not int or not 0 <= relevance <= 3:
                raise ReviewInputError("Judged-paper relevance must be an integer from 0 to 3")
            if not isinstance(rationale, str) or not rationale.strip():
                raise ReviewInputError("Judged papers require a short rationale")
            if reviewer_id is not None:
                if not isinstance(reviewer_id, str) or not reviewer_id.strip():
                    raise ReviewInputError("reviewer_id must be a non-empty string or null")
                provenance_reviewers.add(reviewer_id)
            if annotated_at is not None:
                if not isinstance(annotated_at, str):
                    raise ReviewInputError("annotated_at must be an ISO date or null")
                try:
                    date.fromisoformat(annotated_at)
                except ValueError as exc:
                    raise ReviewInputError("annotated_at must be an ISO date or null") from exc
                provenance_dates.add(annotated_at)
            judgments.append(
                {
                    "arxiv_id": arxiv_id,
                    "relevance": relevance,
                    "rationale": rationale.strip(),
                    **({"reviewer_id": reviewer_id} if reviewer_id else {}),
                    **({"annotated_at": annotated_at} if annotated_at else {}),
                }
            )
        if seen_ids != packet_keys[key]:
            raise ReviewInputError("Annotation file must retain every exact paper ID from its packet case")
        evaluator_cases.append(
            {
                "case_id": case_id,
                "target": target,
                "annotation_status": "judged" if judgments else "unjudged",
                "judgments": judgments,
            }
        )
    if seen_keys != set(packet_keys):
        raise ReviewInputError("Annotation file must retain every case/target from its review packet")
    return {
        "format_version": FORMAT_VERSION,
        "benchmark_id": identity[1],
        "benchmark_version": identity[2],
        "annotation_provenance": {
            "reviewers": sorted(provenance_reviewers),
            "annotation_dates": sorted(provenance_dates),
        },
        "cases": evaluator_cases,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    packet_parser = commands.add_parser("packet", help="Build a review packet and unjudged annotation template")
    packet_parser.add_argument("--queries", required=True)
    packet_parser.add_argument("--snapshots", required=True)
    packet_parser.add_argument("--manifest", required=True)
    packet_parser.add_argument("--packet-out", required=True)
    packet_parser.add_argument("--annotations-out", required=True)
    packet_parser.add_argument("--overwrite", action="store_true")
    convert_parser = commands.add_parser("to-judgments", help="Validate human annotations and emit Phase 4C judgments JSON")
    convert_parser.add_argument("--packet", required=True)
    convert_parser.add_argument("--annotations", required=True)
    convert_parser.add_argument("--judgments-out", required=True)
    convert_parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "packet":
            output_paths = (Path(args.packet_out).resolve(), Path(args.annotations_out).resolve())
            input_paths = {Path(args.queries).resolve(), Path(args.snapshots).resolve(), Path(args.manifest).resolve()}
            if output_paths[0] == output_paths[1] or any(path in input_paths for path in output_paths):
                raise ReviewInputError("Packet/annotation outputs must be distinct from each other and from all inputs")
            queries = _read(args.queries)
            snapshots = _read(args.snapshots)
            manifest = _read(args.manifest)
            packet, annotations = build_packet(queries, snapshots, manifest)
            existing = [path for path in (Path(args.packet_out), Path(args.annotations_out)) if path.exists()]
            if existing and not args.overwrite:
                raise ReviewInputError("Output exists; choose new paths or pass --overwrite explicitly")
            _write_new(args.packet_out, packet, args.overwrite)
            _write_new(args.annotations_out, annotations, args.overwrite)
        else:
            output_path = Path(args.judgments_out).resolve()
            if output_path in {Path(args.packet).resolve(), Path(args.annotations).resolve()}:
                raise ReviewInputError("Judgments output cannot replace the review packet or annotation source")
            packet = _read(args.packet)
            annotations = _read(args.annotations)
            judgments = convert_annotations(packet, annotations)
            _write_new(args.judgments_out, judgments, args.overwrite)
    except ReviewInputError as exc:
        print(f"review input error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
