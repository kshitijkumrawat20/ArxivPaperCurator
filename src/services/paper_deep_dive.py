"""Bounded, paper-scoped retrieval and validated Deep Dive generation."""

import hashlib
import json
import logging
from typing import Any
from urllib.parse import quote

from pydantic import ValidationError

from src.config import Settings, get_settings
from src.respositories.paper_brief import PaperBriefRepository
from src.schema.api.deep_dive import (
    DeepDiveEvidenceReference,
    PaperBriefContent,
    PaperDeepDiveRequest,
    PaperDeepDiveResponse,
)

logger = logging.getLogger(__name__)
PROMPT_VERSION = "paper-deep-dive-v1"
UNAVAILABLE = "Unavailable from the retrieved paper evidence."
EVIDENCE_QUERY = (
    "paper problem statement contributions methodology method architecture algorithm training approach "
    "experiments datasets baselines metrics results limitations implementation code"
)


class PaperDeepDiveNotFoundError(Exception):
    pass


class PaperDeepDiveNotPreparedError(Exception):
    pass


class PaperDeepDiveInsufficientEvidenceError(Exception):
    pass


class PaperDeepDiveSearchUnavailableError(Exception):
    pass


class PaperDeepDiveGenerationUnavailableError(Exception):
    pass


class PaperDeepDivePersistenceError(Exception):
    pass


class PaperDeepDiveService:
    def __init__(
        self,
        paper_repository: Any,
        brief_repository: PaperBriefRepository,
        opensearch_client: Any,
        embeddings_service: Any,
        ollama_client: Any,
        settings: Settings | None = None,
    ):
        self.paper_repository = paper_repository
        self.brief_repository = brief_repository
        self.opensearch_client = opensearch_client
        self.embeddings_service = embeddings_service
        self.ollama_client = ollama_client
        self.settings = settings or get_settings()

    async def generate(self, arxiv_id: str, request: PaperDeepDiveRequest) -> PaperDeepDiveResponse:
        paper = self.paper_repository.get_by_arxiv_id(arxiv_id)
        if paper is None:
            raise PaperDeepDiveNotFoundError(arxiv_id)
        if not (paper.raw_text or "").strip():
            raise PaperDeepDiveNotPreparedError(arxiv_id)

        try:
            if not self.opensearch_client.get_chunks_by_paper(arxiv_id, limit=1, raise_errors=True):
                raise PaperDeepDiveNotPreparedError(arxiv_id)
        except PaperDeepDiveNotPreparedError:
            raise
        except Exception as exc:
            raise PaperDeepDiveSearchUnavailableError("Could not verify paper indexing") from exc

        requested_top_k = min(request.top_k, self.settings.deep_dive.max_chunks)
        retrieval_mode = "bm25"
        embedding = None
        if request.use_hybrid:
            try:
                embedding = await self.embeddings_service.embed_query(EVIDENCE_QUERY)
                retrieval_mode = "hybrid"
            except Exception as exc:
                logger.warning("Deep Dive embedding unavailable; using scoped BM25 (%s)", type(exc).__name__)

        try:
            result = self.opensearch_client.search_unified(
                query=EVIDENCE_QUERY,
                query_embedding=embedding,
                size=requested_top_k,
                from_=0,
                use_hybrid=retrieval_mode == "hybrid",
                min_score=0.0,
                arxiv_id=arxiv_id,
            )
        except Exception as exc:
            raise PaperDeepDiveSearchUnavailableError("Paper-scoped evidence search failed") from exc

        selected_hits = [
            hit for hit in result.get("hits", [])
            if hit.get("arxiv_id") == arxiv_id and hit.get("chunk_id") and hit.get("chunk_text")
        ][:requested_top_k]
        if not selected_hits:
            raise PaperDeepDiveInsufficientEvidenceError(
                "No relevant full-text chunks were retrieved from this paper; no brief was generated."
            )

        contexts, prompt = self._build_bounded_prompt(arxiv_id, selected_hits)
        if not contexts:
            raise PaperDeepDiveInsufficientEvidenceError(
                "The configured prompt limit was too small to include paper evidence; no brief was generated."
            )
        evidence_hash = hashlib.sha256(
            json.dumps(contexts, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()
        cache_args = dict(
            arxiv_id=arxiv_id,
            model=request.model,
            prompt_version=PROMPT_VERSION,
            retrieval_mode=retrieval_mode,
            top_k=requested_top_k,
            evidence_hash=evidence_hash,
        )
        try:
            cached = self.brief_repository.get_compatible(**cache_args)
        except Exception as exc:
            raise PaperDeepDivePersistenceError("Could not read stored Deep Dive brief") from exc
        if cached is not None:
            try:
                brief = PaperBriefContent.model_validate(cached.content)
                brief = self._validate_references(brief, contexts)
                return self._response(arxiv_id, request.model, retrieval_mode, brief, len(contexts), True)
            except (ValidationError, TypeError, ValueError):
                # Invalid/incompatible stored JSON is not treated as a successful cache hit.
                logger.warning("Ignoring invalid stored Deep Dive for %s", arxiv_id)

        try:
            response = await self.ollama_client.generate(
                model=request.model,
                prompt=prompt,
                stream=False,
                format=PaperBriefContent.model_json_schema(),
                options={"temperature": 0},
            )
            raw_output = response.get("response") if response else None
            if not raw_output:
                raise ValueError("Ollama returned no structured response")
            brief = PaperBriefContent.model_validate_json(raw_output)
            brief = self._validate_references(brief, contexts)
        except Exception as exc:
            raise PaperDeepDiveGenerationUnavailableError("Could not generate a valid structured paper brief") from exc

        try:
            self.brief_repository.save(content=brief.model_dump(mode="json"), **cache_args)
        except Exception as exc:
            raise PaperDeepDivePersistenceError("Brief generated, but could not be persisted") from exc
        return self._response(arxiv_id, request.model, retrieval_mode, brief, len(contexts), False)

    def _build_bounded_prompt(self, arxiv_id: str, hits: list[dict[str, Any]]) -> tuple[list[dict[str, str]], str]:
        max_chars = self.settings.deep_dive.max_prompt_chars
        max_chunk_chars = self.settings.deep_dive.max_chunk_chars
        system = (
            "Create a structured research brief using ONLY the exact paper excerpts below. "
            f"The selected paper is arXiv:{arxiv_id}. Never use outside knowledge, other papers, or guesses. "
            "Use the exact unavailable phrase when the excerpts do not establish a field. "
            "Do not invent benchmark numbers, code URLs, dependencies, hardware, compute needs, or limitations. "
            "Keep author-stated limitations separate from your cautious inferred caveats. Engineering takeaways "
            "must label each item as reported_fact or engineering_inference. Cite evidence only with supplied "
            "chunk_id values and exact supporting excerpt text; do not invent page numbers. Return JSON matching schema.\n\n"
            "Required output schema:\n" + json.dumps(PaperBriefContent.model_json_schema(), ensure_ascii=False)
            + "\n\nEvidence excerpts:\n"
        )
        remaining = max_chars - len(system)
        contexts: list[dict[str, str]] = []
        for hit in hits:
            if remaining <= 100:
                break
            chunk_text = str(hit["chunk_text"])[:max_chunk_chars]
            section_name = str(hit.get("section_title") or "")
            prefix = f"\n[chunk_id={hit['chunk_id']}; section={section_name or 'unavailable'}]\n"
            available = remaining - len(prefix)
            excerpt = chunk_text[:min(len(chunk_text), available)]
            if not excerpt.strip():
                continue
            context = {
                "chunk_id": str(hit["chunk_id"]),
                "section_name": section_name,
                "chunk_text": excerpt,
            }
            contexts.append(context)
            rendered = prefix + excerpt + "\n"
            system += rendered
            remaining -= len(rendered)
        return contexts, system

    @staticmethod
    def _validate_references(brief: PaperBriefContent, contexts: list[dict[str, str]]) -> PaperBriefContent:
        by_id = {context["chunk_id"]: context for context in contexts}
        valid_refs: list[DeepDiveEvidenceReference] = []
        removed = False
        for reference in brief.evidence_references:
            context = by_id.get(reference.chunk_id)
            if (
                context is None
                or not reference.excerpt.strip()
                or reference.excerpt not in context["chunk_text"]
                or (reference.section_name and context["section_name"] and reference.section_name != context["section_name"])
            ):
                removed = True
                continue
            valid_refs.append(
                DeepDiveEvidenceReference(
                    chunk_id=reference.chunk_id,
                    section_name=context["section_name"] or None,
                    excerpt=reference.excerpt,
                )
            )
        gaps = list(brief.information_gaps)
        required_scalars = (
            brief.executive_summary,
            brief.problem_statement,
            brief.methodology,
            brief.experimental_results,
            brief.implementation_details,
        )
        required_lists = (
            brief.key_contributions,
            brief.author_stated_limitations,
            brief.system_inferred_caveats,
        )
        if any(value == UNAVAILABLE for value in required_scalars) or any(
            values == [UNAVAILABLE] for values in required_lists
        ) or not brief.practical_engineering_takeaways:
            gaps.append("One or more requested brief sections were unavailable from the retrieved evidence.")
        if removed:
            gaps.append("Some generated evidence references did not match retrieved excerpts and were removed.")
        if not valid_refs:
            gaps.append("No valid supporting excerpt references were returned by the model.")
        return brief.model_copy(update={"evidence_references": valid_refs, "information_gaps": list(dict.fromkeys(gaps))})

    @staticmethod
    def _response(arxiv_id, model, mode, brief, count, cached):
        return PaperDeepDiveResponse(
            arxiv_id=arxiv_id,
            source_url=f"https://arxiv.org/pdf/{quote(arxiv_id, safe='/.')}.pdf",
            model=model,
            prompt_version=PROMPT_VERSION,
            retrieval_mode=mode,
            chunks_used=count,
            cached=cached,
            brief=brief,
        )
