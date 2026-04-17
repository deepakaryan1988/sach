import pytest
from unittest.mock import AsyncMock, patch

from app.models.requests import VerifyRequest
from app.pipeline.verify import VerificationPipeline


@pytest.fixture
def pipeline():
    return VerificationPipeline()


@pytest.fixture
def mock_analyzer_response():
    return '{"rhetoric_score": 0.2, "analysis_details": "Neutral."}'

@pytest.fixture
def mock_judge_response():
    return '{"truth_score": 0.9, "verdict": "Likely True", "explanation": "NASA confirms Earth is round."}'


@pytest.mark.asyncio
async def test_verify_pipeline_valid_query(pipeline, mock_analyzer_response, mock_judge_response):
    with patch.object(
        pipeline.router, "generate", new_callable=AsyncMock
    ) as mock_generate, patch.object(
        pipeline.router, "generate_swarm", new_callable=AsyncMock
    ) as mock_swarm:
        mock_generate.return_value = (mock_analyzer_response, "local")
        mock_swarm.return_value = [mock_judge_response, mock_judge_response, mock_judge_response]
        
        with patch.object(pipeline.searcher, "search", new_callable=AsyncMock) as mock_search:
            from app.models.responses import Source
            mock_search.return_value = [Source(title="Test", content="Data")]
            
            request = VerifyRequest(query="The Sun rises in the East.")
            response = await pipeline.verify(request)

            assert response.query == "The Sun rises in the East."
            assert 0.0 <= response.truth_score <= 1.0
            assert response.verdict in ["Likely True", "Likely False", "Uncertain"]
            assert response.model_used == "swarm (3 models)"
            assert response.latency_ms >= 0


@pytest.mark.asyncio
async def test_verify_pipeline_search_sources(pipeline, mock_analyzer_response, mock_judge_response):
    with patch.object(
        pipeline.router, "generate", new_callable=AsyncMock
    ) as mock_generate, patch.object(
        pipeline.router, "generate_swarm", new_callable=AsyncMock
    ) as mock_swarm:
        mock_generate.return_value = (mock_analyzer_response, "cloud")
        mock_swarm.return_value = [mock_judge_response, mock_judge_response, mock_judge_response]

        with patch.object(pipeline.searcher, "search", new_callable=AsyncMock) as mock_search:
            from app.models.responses import Source
            mock_search.return_value = [Source(title="Test", content="Data")]
            request = VerifyRequest(query="Test claim")
            response = await pipeline.verify(request)

            assert len(response.sources) >= 1
            assert response.model_used == "swarm (3 models)"


@pytest.mark.asyncio
async def test_parse_judge_response_valid_json(pipeline):
    score, verdict, explanation = pipeline._parse_judge_response(
        '{"truth_score": 0.85, "verdict": "Likely True", "explanation": "Test."}'
    )
    assert score == 0.85
    assert verdict == "Likely True"
    assert explanation == "Test."


@pytest.mark.asyncio
async def test_parse_analyzer_response_invalid_json(pipeline):
    score, details = pipeline._parse_analyzer_response("Invalid response")
    assert score == 0.0
    assert details == "Parsing failed."
