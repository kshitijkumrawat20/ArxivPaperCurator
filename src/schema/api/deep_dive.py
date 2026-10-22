"""API contracts for on-demand preparation and structured Paper Deep Dive."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class PaperPreparationResponse(BaseModel):
    arxiv_id: str
    status: Literal["ready"]
    parsed: bool
    indexed: bool
    chunks_indexed: int = Field(ge=0)
    reused_existing_content: bool


class PaperDeepDiveRequest(BaseModel):
    model: str = Field("qwen2.5-coder:1.5b", min_length=1, max_length=100)
    top_k: int = Field(8, ge=1, le=10, description="Maximum evidence chunks to retrieve")
    use_hybrid: bool = Field(True, description="Use scoped hybrid retrieval; falls back only to scoped BM25")


class DeepDiveEvidenceReference(BaseModel):
    chunk_id: str
    section_name: str | None = None
    excerpt: str = Field(min_length=1, max_length=1000)


class EngineeringTakeaway(BaseModel):
    takeaway: str
    basis: Literal["reported_fact", "engineering_inference"]


class PaperBriefContent(BaseModel):
    executive_summary: str = "Unavailable from the retrieved paper evidence."
    problem_statement: str = "Unavailable from the retrieved paper evidence."
    key_contributions: list[str] = Field(default_factory=list)
    methodology: str = "Unavailable from the retrieved paper evidence."
    experimental_results: str = "Unavailable from the retrieved paper evidence."
    author_stated_limitations: list[str] = Field(default_factory=list)
    system_inferred_caveats: list[str] = Field(default_factory=list)
    implementation_details: str = "Unavailable from the retrieved paper evidence."
    practical_engineering_takeaways: list[EngineeringTakeaway] = Field(default_factory=list)
    evidence_references: list[DeepDiveEvidenceReference] = Field(default_factory=list)
    information_gaps: list[str] = Field(default_factory=list)

    @field_validator("key_contributions", "author_stated_limitations", "system_inferred_caveats", mode="before")
    @classmethod
    def make_unavailable_lists_explicit(cls, value):
        if value is None or value == []:
            return ["Unavailable from the retrieved paper evidence."]
        return value

    @field_validator(
        "executive_summary", "problem_statement", "methodology", "experimental_results", "implementation_details",
        mode="before",
    )
    @classmethod
    def normalize_unavailable_fields(cls, value):
        if value is None or (isinstance(value, str) and not value.strip()):
            return "Unavailable from the retrieved paper evidence."
        return value


class PaperDeepDiveResponse(BaseModel):
    arxiv_id: str
    source_url: str
    model: str
    prompt_version: str
    retrieval_mode: Literal["bm25", "hybrid"]
    chunks_used: int = Field(ge=1)
    cached: bool
    brief: PaperBriefContent
