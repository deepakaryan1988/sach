import pytest
from unittest.mock import AsyncMock, patch

from app.models.requests import VerifyRequest
from app.pipeline.verify import VerificationPipeline


@pytest.fixture
def pipeline():
    return VerificationPipeline()


@pytest.fixture
def mock_response():
    return '{"truth_score": 0.9, "verdict": "Likely True", "explanation": "NASA confirms Earth is round."}'


@pytest.mark.asyncio
async def test_verify_pipeline_valid_query(pipeline, mock_response):
    with patch.object(
        pipeline.router, "generate", new_callable=AsyncMock
    ) as mock_generate:
        mock_generate.return_value = (mock_response, "local")
        request = VerifyRequest(query="The Sun rises in the East.")
        response = await pipeline.verify(request)

        assert response.query == "The Sun rises in the East."
        assert 0.0 <= response.truth_score <= 1.0
        assert response.verdict in ["Likely True", "Likely False", "Uncertain"]
        assert response.model_used == "local"
        assert response.latency_ms >= 0


@pytest.mark.asyncio
async def test_verify_pipeline_faiss_sources(pipeline, mock_response):
    with patch.object(
        pipeline.router, "generate", new_callable=AsyncMock
    ) as mock_generate:
        mock_generate.return_value = (mock_response, "cloud")
        request = VerifyRequest(query="Test claim")
        response = await pipeline.verify(request)

        assert len(response.sources) >= 1
        assert response.model_used == "cloud"


@pytest.mark.asyncio
async def test_parse_llm_response_valid_json(pipeline):
    score, verdict, explanation = pipeline._parse_llm_response(
        '{"truth_score": 0.85, "verdict": "Likely True", "explanation": "Test."}'
    )
    assert score == 0.85
    assert verdict == "Likely True"
    assert explanation == "Test."


@pytest.mark.asyncio
async def test_parse_llm_response_invalid_json(pipeline):
    score, verdict, explanation = pipeline._parse_llm_response("Invalid response")
    assert score == 0.5
    assert verdict == "Uncertain"
    assert explanation == "Invalid response"
