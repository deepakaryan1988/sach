import pytest
from unittest.mock import AsyncMock, patch

from app.models.requests import VerifyRequest
from app.models.responses import Source
from app.pipeline.verify import VerificationPipeline, _weighted_median, _tier_weight
from app.pipeline.search import _get_tier, _is_govt_aligned, _get_domain


@pytest.fixture
def pipeline():
    return VerificationPipeline()


# Mock LLM responses for the 3 concurrent agents
MOCK_REFORMULATE = '{"queries": ["sun rises east", "does sun rise in east fact check"]}'
MOCK_ANALYZER = '{"rhetoric_score": 0.2, "analysis_details": "Neutral, factual claim."}'
MOCK_OFFICIAL = '{"is_official": false, "claimant_type": "none", "note": ""}'
MOCK_JUDGE = '{"truth_score": 0.9, "verdict": "Likely True", "explanation": "NASA confirms Earth rotates west-to-east."}'

# Default independence metadata returned by search
DEFAULT_META = {
    "unique_domains": 3,
    "region_coverage": ["India", "International"],
    "govt_aligned_count": 0,
    "govt_aligned_ratio": 0.0,
    "single_origin_warning": False,
    "dominant_domain": None,
}


@pytest.fixture
def mock_sources():
    return [
        Source(
            title="[Tier 1] [India] Reuters: Sun rises East",
            content="URL: https://reuters.com/1\nRegion: India\nArticle excerpt: The sun rises in the east.",
        )
    ]


@pytest.fixture
def mock_search_return(mock_sources):
    """search() now returns (sources, independence_meta)."""
    return (mock_sources, DEFAULT_META)


# ---------------------------------------------------------------------------
# Full pipeline integration tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_verify_pipeline_valid_query(pipeline, mock_search_return):
    with patch.object(pipeline.router, "generate", new_callable=AsyncMock) as mock_generate, \
         patch.object(pipeline.router, "generate_swarm", new_callable=AsyncMock) as mock_swarm, \
         patch.object(pipeline.searcher, "search", new_callable=AsyncMock) as mock_search:

        # generate() called 3 times concurrently: reformulation, rhetoric, official
        mock_generate.side_effect = [
            (MOCK_REFORMULATE, "cloud"),
            (MOCK_ANALYZER, "cloud"),
            (MOCK_OFFICIAL, "cloud"),
        ]
        mock_swarm.return_value = [MOCK_JUDGE, MOCK_JUDGE, MOCK_JUDGE]
        mock_search.return_value = mock_search_return

        request = VerifyRequest(query="The Sun rises in the East.")
        response = await pipeline.verify(request)

        assert response.query == "The Sun rises in the East."
        assert 0.0 <= response.truth_score <= 1.0
        assert response.verdict in ["Likely True", "Likely False", "Uncertain"]
        assert "swarm" in response.model_used
        assert response.latency_ms >= 0
        assert response.rhetoric_score == 0.2
        assert response.is_official_claim is False


@pytest.mark.asyncio
async def test_verify_pipeline_search_sources(pipeline, mock_search_return):
    with patch.object(pipeline.router, "generate", new_callable=AsyncMock) as mock_generate, \
         patch.object(pipeline.router, "generate_swarm", new_callable=AsyncMock) as mock_swarm, \
         patch.object(pipeline.searcher, "search", new_callable=AsyncMock) as mock_search:

        mock_generate.side_effect = [
            (MOCK_REFORMULATE, "cloud"),
            (MOCK_ANALYZER, "cloud"),
            (MOCK_OFFICIAL, "cloud"),
        ]
        mock_swarm.return_value = [MOCK_JUDGE, MOCK_JUDGE]
        mock_search.return_value = mock_search_return

        request = VerifyRequest(query="Test claim")
        response = await pipeline.verify(request)

        assert len(response.sources) >= 1
        assert "swarm" in response.model_used


@pytest.mark.asyncio
async def test_verify_pipeline_swarm_offline_returns_error(pipeline, mock_search_return):
    """If all swarm models fail, the pipeline should return a graceful Error response."""
    with patch.object(pipeline.router, "generate", new_callable=AsyncMock) as mock_generate, \
         patch.object(pipeline.router, "generate_swarm", new_callable=AsyncMock) as mock_swarm, \
         patch.object(pipeline.searcher, "search", new_callable=AsyncMock) as mock_search:

        mock_generate.side_effect = [
            (MOCK_REFORMULATE, "cloud"),
            (MOCK_ANALYZER, "cloud"),
            (MOCK_OFFICIAL, "cloud"),
        ]
        mock_swarm.return_value = []
        mock_search.return_value = mock_search_return

        request = VerifyRequest(query="Swarm offline test")
        response = await pipeline.verify(request)

        assert response.verdict == "Error"
        assert response.truth_score == 0.0
        assert response.model_used == "Offline"


@pytest.mark.asyncio
async def test_rhetoric_penalty_applied(pipeline, mock_search_return):
    """A high rhetoric score should pull the final truth score toward 0.5."""
    high_rhetoric = '{"rhetoric_score": 0.9, "analysis_details": "Highly manipulative."}'
    with patch.object(pipeline.router, "generate", new_callable=AsyncMock) as mock_generate, \
         patch.object(pipeline.router, "generate_swarm", new_callable=AsyncMock) as mock_swarm, \
         patch.object(pipeline.searcher, "search", new_callable=AsyncMock) as mock_search:

        mock_generate.side_effect = [
            (MOCK_REFORMULATE, "cloud"),
            (high_rhetoric, "cloud"),
            (MOCK_OFFICIAL, "cloud"),
        ]
        mock_swarm.return_value = [MOCK_JUDGE]
        mock_search.return_value = mock_search_return

        request = VerifyRequest(query="A very biased viral claim!")
        response = await pipeline.verify(request)

        assert response.truth_score < 0.9
        assert response.rhetoric_score == 0.9


@pytest.mark.asyncio
async def test_official_claim_penalty(pipeline, mock_search_return):
    """Claims from politicians with high govt-aligned source ratio get penalised."""
    official_response = '{"is_official": true, "claimant_type": "politician", "note": "PM claimed this."}'
    # Use a meta with high govt_aligned_ratio to trigger penalty
    govt_meta = {**DEFAULT_META, "govt_aligned_ratio": 0.6, "govt_aligned_count": 3}
    with patch.object(pipeline.router, "generate", new_callable=AsyncMock) as mock_generate, \
         patch.object(pipeline.router, "generate_swarm", new_callable=AsyncMock) as mock_swarm, \
         patch.object(pipeline.searcher, "search", new_callable=AsyncMock) as mock_search:

        mock_generate.side_effect = [
            (MOCK_REFORMULATE, "cloud"),
            (MOCK_ANALYZER, "cloud"),
            (official_response, "cloud"),
        ]
        mock_swarm.return_value = [MOCK_JUDGE]
        mock_search.return_value = (mock_search_return[0], govt_meta)

        request = VerifyRequest(query="PM says India's GDP grew 12%")
        response = await pipeline.verify(request)

        assert response.is_official_claim is True
        assert response.truth_score < 0.9  # Penalised
        assert "Official Claim Penalty" in response.explanation


@pytest.mark.asyncio
async def test_circular_reporting_penalty(pipeline, mock_sources):
    """Sources dominated by one domain should trigger a circular reporting penalty."""
    circular_meta = {
        **DEFAULT_META,
        "single_origin_warning": True,
        "dominant_domain": "ani.in",
    }
    with patch.object(pipeline.router, "generate", new_callable=AsyncMock) as mock_generate, \
         patch.object(pipeline.router, "generate_swarm", new_callable=AsyncMock) as mock_swarm, \
         patch.object(pipeline.searcher, "search", new_callable=AsyncMock) as mock_search:

        mock_generate.side_effect = [
            (MOCK_REFORMULATE, "cloud"),
            (MOCK_ANALYZER, "cloud"),
            (MOCK_OFFICIAL, "cloud"),
        ]
        mock_swarm.return_value = [MOCK_JUDGE]
        mock_search.return_value = (mock_sources, circular_meta)

        request = VerifyRequest(query="ANI reports new policy launched")
        response = await pipeline.verify(request)

        assert response.truth_score < 0.9
        assert "Circular Reporting Penalty" in response.explanation


@pytest.mark.asyncio
async def test_narrative_divergence_detection(pipeline):
    """When domestic and international sources both exist, divergence should be flagged."""
    domestic = Source(title="[Tier 3] [India] NDTV: Claim X confirmed", content="URL: https://ndtv.com/1\nRegion: India\nSnippet: Claim X")
    intl = Source(title="[Tier 1] [International] Reuters: Claim X disputed", content="URL: https://reuters.com/2\nRegion: International\nSnippet: Claim X disputed")
    assert pipeline._detect_narrative_divergence([domestic, intl]) is True
    assert pipeline._detect_narrative_divergence([domestic]) is False


# ---------------------------------------------------------------------------
# Unit tests: parsing helpers
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_parse_judge_response_valid_json(pipeline):
    score, verdict, explanation = pipeline._parse_judge_response(
        '{"truth_score": 0.85, "verdict": "Likely True", "explanation": "Test."}'
    )
    assert score == 0.85
    assert verdict == "Likely True"
    assert explanation == "Test."


@pytest.mark.asyncio
async def test_parse_judge_response_invalid_json_fallback(pipeline):
    score, verdict, explanation = pipeline._parse_judge_response("Invalid response")
    assert score == 0.5
    assert verdict == "Uncertain"
    assert explanation == "Invalid response"


@pytest.mark.asyncio
async def test_parse_analyzer_response_invalid_json(pipeline):
    score, details = pipeline._parse_analyzer_response("Invalid response")
    assert score == 0.0
    assert details == "Parsing failed."


@pytest.mark.asyncio
async def test_parse_official_response_valid(pipeline):
    is_official, ctype, note = pipeline._parse_official_response(
        '{"is_official": true, "claimant_type": "government", "note": "Ministry of Health"}'
    )
    assert is_official is True
    assert ctype == "government"
    assert note == "Ministry of Health"


@pytest.mark.asyncio
async def test_parse_official_response_invalid(pipeline):
    is_official, ctype, note = pipeline._parse_official_response("garbage")
    assert is_official is False
    assert ctype == "none"


# ---------------------------------------------------------------------------
# Unit tests: scoring helpers
# ---------------------------------------------------------------------------

def test_weighted_median_basic():
    assert _weighted_median([0.2, 0.5, 0.9], [1.0, 1.0, 1.0]) == 0.5


def test_weighted_median_single():
    assert _weighted_median([0.7], [1.0]) == 0.7


def test_weighted_median_empty():
    assert _weighted_median([], []) == 0.5


def test_weighted_median_outlier_resistance():
    scores = [0.8, 0.85, 0.0]
    weights = [1.0, 1.0, 1.0]
    result = _weighted_median(scores, weights)
    assert result == 0.8


def test_tier_weight_extreme_scores_penalised():
    w_extreme = _tier_weight("some-model", 1.0)
    w_moderate = _tier_weight("some-model", 0.6)
    assert w_extreme < w_moderate


def test_tier_weight_minimum_floor():
    assert _tier_weight("model", 1.0) >= 0.3
    assert _tier_weight("model", 0.0) >= 0.3


# ---------------------------------------------------------------------------
# Unit tests: search module helpers
# ---------------------------------------------------------------------------

def test_get_tier_known_domain():
    assert _get_tier("https://reuters.com/article/123") == 1
    assert _get_tier("https://www.altnews.in/fact-check") == 2
    assert _get_tier("https://www.infowars.com/post") == 5


def test_get_tier_unknown_defaults_to_3():
    assert _get_tier("https://randomsite.xyz/page") == 3


def test_is_govt_aligned():
    assert _is_govt_aligned("https://www.ani.in/news/123") is True
    assert _is_govt_aligned("https://pti.in/story") is True
    assert _is_govt_aligned("https://reuters.com/article") is False


def test_get_domain():
    assert _get_domain("https://www.reuters.com/article/123") == "reuters.com"
    assert _get_domain("https://ani.in/news") == "ani.in"
