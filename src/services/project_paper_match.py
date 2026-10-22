"""Stateless, metadata-only Project-to-Paper matching."""

import logging
import re
from datetime import date, datetime
from typing import Any
from urllib.parse import quote

from src.schema.api.project_match import (
    ProjectMatchPaper,
    ProjectMatchRequest,
    ProjectMatchResponse,
    ProjectMatchSignal,
    ProjectQueryContext,
)
from src.services.metadata_discovery import MetadataDiscoveryService

logger = logging.getLogger(__name__)
MAX_SEARCH_QUERY_CHARS = 500
MAX_ABSTRACT_CHARS = 1000
MAX_MATCH_SIGNALS = 8
STOPWORDS = {
    "about", "across", "after", "also", "among", "and", "are", "based", "build", "building",
    "can", "could", "data", "for", "from", "have", "help", "how", "into", "its", "make",
    "method", "methods", "model", "models", "more", "new", "our", "paper", "project", "research",
    "results", "should", "solution", "study", "system", "systems", "that", "the", "their", "these",
    "this", "through", "using", "use", "we", "with", "would", "work", "which", "while", "will",
    "machine", "learning", "artificial", "intelligence", "ai", "ml",
}


class ProjectMatchSearchUnavailableError(Exception):
    pass


class ProjectPaperMatchService:
    """Search the shared metadata index; no PDF, embedding, or LLM work is done."""

    def __init__(self, opensearch_client: Any):
        self.discovery = MetadataDiscoveryService(opensearch_client)

    def match(self, request: ProjectMatchRequest) -> ProjectMatchResponse:
        search_query = self._build_query(request)
        context = ProjectQueryContext(
            project_title=request.project_title or None,
            project_description=request.project_description,
            technologies=request.technologies,
            research_interests=request.research_interests,
            categories=request.categories,
            date_from=request.date_from,
            date_to=request.date_to,
            search_query=search_query,
        )
        # MetadataDiscoveryService builds category/date constraints directly into
        # the metadata-index query. There is no chunk-index/global-search fallback.
        try:
            result = self.discovery.search(
                query=search_query,
                size=request.top_k,
                from_=0,
                categories=request.categories or None,
                date_from=request.date_from,
                date_to=request.date_to,
            )
        except Exception as exc:
            raise ProjectMatchSearchUnavailableError("Metadata search is unavailable") from exc
        candidates = []
        seen_exact_ids = set()
        terms = [term for term in self._match_terms(request) if self._find_term(search_query, term) is not None]
        for hit in result.get("hits", []):
            arxiv_id = str(hit.get("arxiv_id") or "")
            if not arxiv_id or arxiv_id in seen_exact_ids:
                continue
            seen_exact_ids.add(arxiv_id)
            title = str(hit.get("title") or "")
            abstract = str(hit.get("abstract") or "")
            categories = [str(category) for category in (hit.get("categories") or [])]
            signals = self._signals(title, abstract, categories, terms, request.categories)
            published_date = hit.get("published_date") or ""
            if isinstance(published_date, (date, datetime)):
                published_date = published_date.isoformat()
            pdf_url = hit.get("pdf_url") or None
            if not pdf_url:
                pdf_url = f"https://arxiv.org/pdf/{quote(arxiv_id, safe='/.')}.pdf"
            candidates.append(
                ProjectMatchPaper(
                    retrieval_rank=len(candidates) + 1,
                    arxiv_id=arxiv_id,
                    title=title,
                    abstract_excerpt=abstract[:MAX_ABSTRACT_CHARS],
                    authors=[str(author) for author in (hit.get("authors") or [])],
                    categories=categories,
                    published_date=str(published_date),
                    pdf_url=hit.get("pdf_url") or None,
                    source_url=hit.get("source_url") or pdf_url,
                    search_score=hit.get("score"),
                    match_signals=signals,
                )
            )

        return ProjectMatchResponse(
            query_context=context,
            result_count=len(candidates),
            total_candidates=int(result.get("total", 0) or 0),
            message=(
                "No papers matched the supplied project context and filters. Try broadening the description, categories, or date range."
                if not candidates else None
            ),
            papers=candidates,
        )

    @staticmethod
    def _build_query(request: ProjectMatchRequest) -> str:
        parts = [request.project_title or "", request.project_description]
        parts.extend(request.technologies)
        parts.extend(request.research_interests)
        compact = re.sub(r"\s+", " ", " ".join(part.strip() for part in parts if part.strip()))
        return compact[:MAX_SEARCH_QUERY_CHARS].strip()

    @staticmethod
    def _match_terms(request: ProjectMatchRequest) -> list[str]:
        explicit = [request.project_title or "", *request.technologies, *request.research_interests]
        explicit_tokens = [
            token for value in explicit
            for token in re.findall(r"[A-Za-z][A-Za-z0-9.+#]*", value)
            if len(token) >= 3 and token.casefold() not in STOPWORDS
        ]
        description_terms = [
            token for token in re.findall(r"[A-Za-z][A-Za-z0-9.+#]*", request.project_description)
            if len(token) >= 3 and token.casefold() not in STOPWORDS
        ]
        terms = []
        seen = set()
        for term in [*explicit, *explicit_tokens, *description_terms]:
            term = re.sub(r"\s+", " ", term).strip()
            key = term.casefold()
            if term and key not in seen and key not in STOPWORDS:
                terms.append(term)
                seen.add(key)
            if len(terms) >= 30:
                break
        return terms

    @staticmethod
    def _find_term(text: str, term: str) -> int | None:
        haystack = text.casefold()
        needle = term.casefold()
        cursor = 0
        while needle:
            index = haystack.find(needle, cursor)
            if index < 0:
                return None
            end = index + len(needle)
            left_ok = not needle[0].isalnum() or index == 0 or not haystack[index - 1].isalnum()
            right_ok = not needle[-1].isalnum() or end == len(haystack) or not haystack[end].isalnum()
            if left_ok and right_ok:
                return index
            cursor = index + 1
        return None

    @classmethod
    def _signals(
        cls, title: str, abstract: str, categories: list[str], terms: list[str], requested_categories: list[str]
    ) -> list[ProjectMatchSignal]:
        signals: list[ProjectMatchSignal] = []
        for category in categories:
            if any(category.casefold() == selected.casefold() for selected in requested_categories):
                signals.append(ProjectMatchSignal(
                    source_field="categories", term=category, evidence_excerpt=category
                ))
        for field_name, text in (("title", title), ("abstract", abstract)):
            for term in terms:
                index = cls._find_term(text, term)
                if index is None:
                    continue
                start = max(0, index - 70)
                end = min(len(text), index + len(term) + 110)
                excerpt = text[start:end].strip()
                if start:
                    excerpt = "…" + excerpt
                if end < len(text):
                    excerpt += "…"
                signals.append(ProjectMatchSignal(
                    source_field=field_name, term=term, evidence_excerpt=excerpt
                ))
                if len(signals) >= MAX_MATCH_SIGNALS:
                    return signals
        return signals[:MAX_MATCH_SIGNALS]
