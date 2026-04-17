from typing import List

from pydantic import BaseModel, Field


class Source(BaseModel):
    title: str = Field(..., description="Source document title")
    content: str = Field(..., description="Relevant content from source")


class SwarmMember(BaseModel):
    model_name: str
    truth_score: float
    explanation: str


class SourceIndependence(BaseModel):
    unique_domains: int = Field(0, description="Number of distinct source domains")
    region_coverage: List[str] = Field(default_factory=list, description="Regions that returned results")
    govt_aligned_ratio: float = Field(0.0, ge=0.0, le=1.0, description="Fraction of sources from govt-aligned wires")
    single_origin_warning: bool = Field(False, description="True if >50% of sources come from one domain")
    dominant_domain: str = Field("", description="The domain that appears most frequently")
    narrative_divergence: bool = Field(False, description="True if domestic and international sources disagree")


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
    source_independence: SourceIndependence = Field(
        default_factory=SourceIndependence,
        description="Analysis of how independent the evidence sources are from each other"
    )
    is_official_claim: bool = Field(
        False, description="True if the claim originates from a political figure or government body"
    )
    model_used: str = Field(..., description="Model used: local or cloud")
    latency_ms: float = Field(
        ..., ge=0.0, description="Response latency in milliseconds"
    )
