import pytest
from unittest.mock import AsyncMock, patch

from app.models.requests import VerifyRequest
from app.models.responses import Source
from app.pipeline.verify import VerificationPipeline, _weighted_median, _tier_weight


@pytest.fixture
def pipeline():
    return VerificationPipeline()


# Reformulation returns a list of queries; analyzer and judge return their respective JSON
MOCK_REFORMULATE = '{"queries": ["sun rises east", "does sun rise in east fact check"]}'
MOCK_ANALYZER = '{"rhetoric_score": 0.2, "analysis_details": "Neutral, factual claim."}'
MOCK_JUDGE = '{"truth_score": 0.9, "verdict": "Likely True", "explanation": "NASA confirms Earth rotates west-to-east."}'


@pytest.fixture
def mock_sources():
    return [Source(title="[Tier 1] Reuters: Sun rises East", content="URL: https://reuters.com/1\nArticle excerpt: The sun rises in the east.")]


# ---------------------------------------------------------------------------
# Full pipeline integration tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_verify_pipeline_valid_query(pipeline, mock_sources):
    with patch.object(pipeline.router, "generate", new_callable=AsyncMock) as mock_generate, \
         patch.object(pipeline.router, "generate_swarm", new_callable=AsyncMock) as mock_swarm, \
         patch.object(pipeline.searcher, "search", new_callable=AsyncMock) as mock_search:

        # generate() is called twice: reformulation + rhetoric analysis
        mock_generate.side_effect = [
            (MOCK_REFORMULATE, "cloud"),
            (MOCK_ANALYZER, "cloud"),
        ]
        mock_swarm.return_value = [MOCK_JUDGE, MOCK_JUDGE, MOCK_JUDGE]
        mock_search.return_value = mock_sources

        request = VerifyRequest(query="The Sun rises in the East.")
        response = await pipeline.verify(request)

        assert response.query == "The Sun rises in the East."
        assert 0.0 <= response.truth_score <= 1.0
        assert response.verdict in ["Likely True", "Likely False", "Uncertain"]
        assert "swarm" in response.model_used
        assert response.latency_ms >= 0
        assert response.rhetoric_score == 0.2


@pytest.mark.asyncio
async def test_verify_pipeline_search_sources(pipeline, mock_sources):
    with patch.object(pipeline.router, "generate", new_callable=AsyncMock) as mock_generate, \
         patch.object(pipeline.router, "generate_swarm", new_callable=AsyncMock) as mock_swarm, \
         patch.object(pipeline.searcher, "search", new_callable=AsyncMock) as mock_search:

        mock_generate.side_effect = [
            (MOCK_REFORMULATE, "cloud"),
            (MOCK_ANALYZER, "cloud"),
        ]
        mock_swarm.return_value = [MOCK_JUDGE, MOCK_JUDGE]
        mock_search.return_value = mock_sources

        request = VerifyRequest(query="Test claim")
        response = await pipeline.verify(request)

        assert len(response.sources) >= 1
        assert "swarm" in response.model_used


@pytest.mark.asyncio
async def test_verify_pipeline_swarm_offline_returns_error(pipeline, mock_sources):
    """If all swarm models fail, the pipeline should return a graceful Error response."""
    with patch.object(pipeline.router, "generate", new_callable=AsyncMock) as mock_generate, \
         patch.object(pipeline.router, "generate_swarm", new_callable=AsyncMock) as mock_swarm, \
         patch.object(pipeline.searcher, "search", new_callable=AsyncMock) as mock_search:

        mock_generate.side_effect = [
            (MOCK_REFORMULATE, "cloud"),
            (MOCK_ANALYZER, "cloud"),
        ]
        mock_swarm.return_value = []  # All models failed
        mock_search.return_value = mock_sources

        request = VerifyRequest(query="Swarm offline test")
        response = await pipeline.verify(request)

        assert response.verdict == "Error"
        assert response.truth_score == 0.0
        assert response.model_used == "Offline"


@pytest.mark.asyncio
async def test_rhetoric_penalty_applied(pipeline, mock_sources):
    """A high rhetoric score should pull the final truth score toward 0.5."""
    high_rhetoric_analyzer = '{"rhetoric_score": 0.9, "analysis_details": "Highly manipulative."}'
    # Judge says 0.9 truth, but rhetoric penalty should bring it down
    with patch.object(pipeline.router, "generate", new_callable=AsyncMock) as mock_generate, \
         patch.object(pipeline.router, "generate_swarm", new_callable=AsyncMock) as mock_swarm, \
         patch.object(pipeline.searcher, "search", new_callable=AsyncMock) as mock_search:

        mock_generate.side_effect = [
            (MOCK_REFORMULATE, "cloud"),
            (high_rhetoric_analyzer, "cloud"),
        ]
        mock_swarm.return_value = [MOCK_JUDGE]
        mock_search.return_value = mock_sources

        request = VerifyRequest(query="A very biased viral claim!")
        response = await pipeline.verify(request)

        # With rhetoric 0.9 and judge score 0.9, penalty = 0.9*0.15 = 0.135
        # Expected: 0.9 - 0.135 = 0.765 (still Likely True but lower than raw 0.9)
        assert response.truth_score < 0.9
        assert response.rhetoric_score == 0.9


# ---------------------------------------------------------------------------
# Unit tests for parsing and scoring helpers
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


def test_weighted_median_basic():
    # All equal weights — median of [0.2, 0.5, 0.9] should be 0.5
    assert _weighted_median([0.2, 0.5, 0.9], [1.0, 1.0, 1.0]) == 0.5


def test_weighted_median_single():
    assert _weighted_median([0.7], [1.0]) == 0.7


def test_weighted_median_empty():
    assert _weighted_median([], []) == 0.5


def test_weighted_median_outlier_resistance():
    # One outlier at 0.0 with equal weight — median should not be dragged to mean
    scores = [0.8, 0.85, 0.0]
    weights = [1.0, 1.0, 1.0]
    result = _weighted_median(scores, weights)
    # Median of sorted [0.0, 0.8, 0.85] = 0.8
    assert result == 0.8


def test_tier_weight_extreme_scores_penalised():
    # A model returning 1.0 (fully certain) should get a lower weight
    w_extreme = _tier_weight("some-model", 1.0)
    w_moderate = _tier_weight("some-model", 0.6)
    assert w_extreme < w_moderate


def test_tier_weight_minimum_floor():
    # Weight should never go below 0.3
    assert _tier_weight("model", 1.0) >= 0.3
    assert _tier_weight("model", 0.0) >= 0.3
