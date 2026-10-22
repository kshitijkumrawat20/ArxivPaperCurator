"""Request and response schemas for the metadata-only research radar."""

from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator


Topic = Annotated[str, Field(min_length=1, max_length=120)]
Category = Annotated[str, Field(min_length=2, max_length=32, pattern=r"^[A-Za-z][A-Za-z0-9.-]*$")]


class ResearchRadarRequest(BaseModel):
    topics: list[Topic] = Field(min_length=1, max_length=8)
    categories: list[Category] = Field(default_factory=list, max_length=20)
    lookback_days: int = Field(default=30, ge=1, le=365)
    top_k: int = Field(default=10, ge=1, le=20)
    per_topic_candidate_limit: int = Field(default=20, ge=1, le=50)

    @field_validator("topics", mode="before")
    @classmethod
    def normalize_topics(cls, values):
        if not isinstance(values, list):
            return values
        if len(values) > 8:
            raise ValueError("at most 8 topics may be submitted")
        normalized = []
        seen = set()
        for value in values:
            if not isinstance(value, str):
                return values
            topic = " ".join(value.split())
            key = topic.casefold()
            if topic and key not in seen:
                normalized.append(topic)
                seen.add(key)
        return normalized

    @field_validator("categories", mode="before")
    @classmethod
    def normalize_categories(cls, values):
        if values is None:
            return []
        if not isinstance(values, list):
            return values
        if len(values) > 20:
            raise ValueError("at most 20 categories may be submitted")
        normalized = []
        seen = set()
        for value in values:
            if isinstance(value, str):
                category = value.strip()
                key = category.casefold()
                if category and key not in seen:
                    normalized.append(category)
                    seen.add(key)
        return normalized

    @field_validator("topics")
    @classmethod
    def validate_total_topic_length(cls, topics: list[str]) -> list[str]:
        if sum(len(topic) for topic in topics) + max(0, len(topics) - 1) > 500:
            raise ValueError("combined topic text must not exceed 500 characters")
        return topics


class ResearchRadarDateWindow(BaseModel):
    start_date: date
    end_date: date
    lookback_days: int
    semantics: Literal["inclusive publication dates"] = "inclusive publication dates"


class ResearchRadarSignal(BaseModel):
    topic: str
    source_field: Literal["title", "abstract", "categories"]
    evidence_excerpt: str = Field(max_length=220)


class ResearchRadarPaper(BaseModel):
    arxiv_id: str
    title: str = Field(max_length=500)
    abstract_excerpt: str = Field(max_length=1000)
    authors: list[str] = Field(max_length=50)
    categories: list[str] = Field(max_length=50)
    published_date: str = Field(max_length=40)
    pdf_url: str | None = Field(default=None, max_length=500)
    source_url: str | None = Field(default=None, max_length=500)
    overall_rank: int = Field(ge=1)
    fusion_score: float = Field(ge=0)
    matched_topics: list[str] = Field(max_length=8)
    match_signals: list[ResearchRadarSignal] = Field(default_factory=list, max_length=8)


class ResearchRadarWarning(BaseModel):
    topic: str
    message: str


class ResearchRadarResponse(BaseModel):
    topics: list[str]
    date_window: ResearchRadarDateWindow
    categories: list[str]
    result_count: int = Field(ge=0)
    total_candidates: int = Field(ge=0)
    fusion_method: Literal["Reciprocal Rank Fusion (RRF), k=60; ranking signal, not probability"] = (
        "Reciprocal Rank Fusion (RRF), k=60; ranking signal, not probability"
    )
    message: str | None = None
    warnings: list[ResearchRadarWarning] = Field(default_factory=list, max_length=8)
    papers: list[ResearchRadarPaper]
