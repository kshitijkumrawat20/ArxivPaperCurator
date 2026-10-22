"""Request/response schemas for metadata-first project matching."""

from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


InputTerm = Annotated[str, Field(min_length=1, max_length=100)]
Category = Annotated[str, Field(min_length=2, max_length=32, pattern=r"^[A-Za-z][A-Za-z0-9.-]*$")]


class ProjectMatchRequest(BaseModel):
    project_description: str = Field(..., min_length=1, max_length=2000)
    project_title: str | None = Field(None, max_length=200)
    technologies: list[InputTerm] = Field(default_factory=list, max_length=20)
    research_interests: list[InputTerm] = Field(default_factory=list, max_length=20)
    categories: list[Category] = Field(default_factory=list, max_length=20)
    date_from: date | None = None
    date_to: date | None = None
    top_k: int = Field(default=10, ge=1, le=20)

    @field_validator("project_description", "project_title", mode="before")
    @classmethod
    def strip_text(cls, value):
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("technologies", "research_interests", "categories", mode="before")
    @classmethod
    def normalize_lists(cls, values):
        if values is None:
            return []
        if not isinstance(values, list):
            return values
        normalized = []
        seen = set()
        for value in values:
            if isinstance(value, str):
                value = value.strip()
                key = value.casefold()
                if value and key not in seen:
                    normalized.append(value)
                    seen.add(key)
        return normalized

    @model_validator(mode="after")
    def validate_date_range(self):
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("date_from must be on or before date_to")
        return self


class ProjectQueryContext(BaseModel):
    project_title: str | None
    project_description: str
    technologies: list[str]
    research_interests: list[str]
    categories: list[str]
    date_from: date | None
    date_to: date | None
    search_query: str


class ProjectMatchSignal(BaseModel):
    source_field: Literal["title", "abstract", "categories"]
    term: str
    evidence_excerpt: str


class ProjectMatchPaper(BaseModel):
    retrieval_rank: int = Field(ge=1)
    arxiv_id: str
    title: str
    abstract_excerpt: str
    authors: list[str]
    categories: list[str]
    published_date: str
    pdf_url: str | None = None
    source_url: str | None = None
    search_score: float | None = None
    match_signals: list[ProjectMatchSignal] = Field(default_factory=list)


class ProjectMatchResponse(BaseModel):
    query_context: ProjectQueryContext
    result_count: int = Field(ge=0)
    total_candidates: int = Field(ge=0)
    score_semantics: Literal["OpenSearch metadata BM25 score; not a calibrated probability"] = (
        "OpenSearch metadata BM25 score; not a calibrated probability"
    )
    message: str | None = None
    papers: list[ProjectMatchPaper]
