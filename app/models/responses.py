from typing import List

from pydantic import BaseModel, Field


class Source(BaseModel):
    title: str = Field(..., description="Source document title")
    content: str = Field(..., description="Relevant content from source")


class SwarmMember(BaseModel):
    model_name: str
    truth_score: float
    explanation: str


class VerifyResponse(BaseModel):
    query: str = Field(..., description="Original query")
    truth_score: float = Field(
        ..., ge=0.0, le=1.0, description="Truth score between 0.0 and 1.0"
    )
    verdict: str = Field(
        ..., description="Verdict: Likely True / Likely False / Uncertain"
    )
    sources: List[Source] = Field(default_factory=list, description="Retrieved sources")
    explanation: str = Field(..., description="Detailed explanation")
    rhetoric_score: float = Field(
        0.0, ge=0.0, le=1.0, description="Score indicating presence of propaganda rhetoric"
    )
    swarm_agreement: float = Field(
        1.0, ge=0.0, le=1.0, description="Agreement level between the Swarm LLMs (1.0 = Unanimous)"
    )
    analysis_details: str = Field(
        "", description="Details from the analyzer agent on source contradictions or rhetoric"
    )
    swarm_details: List[SwarmMember] = Field(
        default_factory=list, description="Breakdown of individual model thoughts"
    )
    model_used: str = Field(..., description="Model used: local or cloud")
    latency_ms: float = Field(
        ..., ge=0.0, description="Response latency in milliseconds"
    )
