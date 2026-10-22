"""Multi-topic metadata search combined with rank-based Reciprocal Rank Fusion."""

from datetime import date, datetime, timedelta, timezone
from typing import Any

from src.schema.api.research_radar import (
    ResearchRadarDateWindow,
    ResearchRadarPaper,
    ResearchRadarRequest,
    ResearchRadarResponse,
    ResearchRadarSignal,
    ResearchRadarWarning,
)
from src.services.metadata_discovery import MetadataDiscoveryService

RRF_K = 60
MAX_ABSTRACT_CHARS = 1000
MAX_SIGNALS_PER_PAPER = 8


class ResearchRadarUnavailableError(Exception):
    """Raised when every per-topic metadata search fails."""


class ResearchRadarService:
    def __init__(self, opensearch_client: Any, *, today_provider=None):
        self.discovery = MetadataDiscoveryService(opensearch_client)
        self.today_provider = today_provider or (lambda: datetime.now(timezone.utc).date())

    def search(self, request: ResearchRadarRequest) -> ResearchRadarResponse:
        end_date = self.today_provider()
        start_date = end_date - timedelta(days=request.lookback_days - 1)
        date_window = ResearchRadarDateWindow(
            start_date=start_date,
            end_date=end_date,
            lookback_days=request.lookback_days,
        )

        papers_by_id: dict[str, dict[str, Any]] = {}
        warnings = []
        successful_searches = 0
        for topic in request.topics:
            try:
                result = self.discovery.search(
                    query=topic,
                    size=request.per_topic_candidate_limit,
                    from_=0,
                    categories=request.categories or None,
                    date_from=start_date,
                    date_to=end_date,
                )
            except Exception as exc:
                warnings.append(
                    ResearchRadarWarning(
                        topic=topic,
                        message="Metadata search failed for this topic; its results are not included.",
                    )
                )
                continue

            successful_searches += 1
            seen_in_topic = set()
            for rank, hit in enumerate(result.get("hits", []), start=1):
                arxiv_id = str(hit.get("arxiv_id") or "")
                if not arxiv_id or arxiv_id in seen_in_topic:
                    continue
                seen_in_topic.add(arxiv_id)
                candidate = papers_by_id.setdefault(arxiv_id, self._candidate(hit))
                candidate["fusion_score"] += 1 / (RRF_K + rank)
                candidate["matched_topics"].append(topic)
                candidate["match_signals"].extend(
                    self._signals(topic, hit, candidate["match_signals"])
                )

        if successful_searches == 0:
            raise ResearchRadarUnavailableError("All metadata topic searches failed")

        ordered = sorted(
            papers_by_id.values(),
            key=lambda candidate: (
                -candidate["fusion_score"],
                -self._date_ordinal(candidate["published_date"]),
                candidate["arxiv_id"],
            ),
        )[: request.top_k]
        output = [
            ResearchRadarPaper(
                **candidate,
                overall_rank=rank,
            )
            for rank, candidate in enumerate(ordered, start=1)
        ]
        return ResearchRadarResponse(
            topics=request.topics,
            date_window=date_window,
            categories=request.categories,
            result_count=len(output),
            total_candidates=len(papers_by_id),
            message=(
                "No papers matched the supplied topics and filters. Try broadening the topics, categories, or lookback window."
                if not output
                else None
            ),
            warnings=warnings,
            papers=output,
        )

    @staticmethod
    def _candidate(hit: dict[str, Any]) -> dict[str, Any]:
        published = hit.get("published_date") or ""
        if isinstance(published, (date, datetime)):
            published = published.isoformat()
        authors = [str(author)[:200] for author in (hit.get("authors") or [])[:50]]
        categories = [str(category)[:32] for category in (hit.get("categories") or [])[:50]]
        abstract = str(hit.get("abstract") or "")
        pdf_url = hit.get("pdf_url") or None
        return {
            "arxiv_id": str(hit["arxiv_id"]),
            "title": str(hit.get("title") or "")[:500],
            "abstract_excerpt": abstract[:MAX_ABSTRACT_CHARS],
            "authors": authors,
            "categories": categories,
            "published_date": str(published)[:40],
            "pdf_url": str(pdf_url)[:500] if pdf_url else None,
            "source_url": str(hit.get("source_url") or pdf_url)[:500] if (hit.get("source_url") or pdf_url) else None,
            "fusion_score": 0.0,
            "matched_topics": [],
            "match_signals": [],
        }

    @staticmethod
    def _signals(topic: str, hit: dict[str, Any], existing: list[ResearchRadarSignal]) -> list[ResearchRadarSignal]:
        additions = []
        topic_key = topic.casefold()
        fields = [("title", hit.get("title") or ""), ("abstract", hit.get("abstract") or "")]
        fields.extend(
            ("categories", category)
            for category in (hit.get("categories") or [])
            if str(category).casefold() == topic_key
        )
        for field_name, value in fields:
            text = str(value)
            index = text.casefold().find(topic_key)
            if index < 0:
                continue
            start = max(0, index - 60)
            end = min(len(text), index + len(topic) + 100)
            excerpt = text[start:end].strip()
            if start:
                excerpt = "…" + excerpt
            if end < len(text):
                excerpt += "…"
            signal = ResearchRadarSignal(topic=topic, source_field=field_name, evidence_excerpt=excerpt)
            if not any(
                old.topic.casefold() == topic_key
                and old.source_field == signal.source_field
                and old.evidence_excerpt == signal.evidence_excerpt
                for old in [*existing, *additions]
            ):
                additions.append(signal)
            if len(existing) + len(additions) >= MAX_SIGNALS_PER_PAPER:
                break
        return additions

    @staticmethod
    def _date_ordinal(value: str) -> int:
        try:
            return date.fromisoformat(value[:10]).toordinal()
        except (TypeError, ValueError):
            return 0
