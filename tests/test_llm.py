import pytest

from app.llm.ollama import OllamaClient
from app.llm.openrouter import OpenRouterClient
from app.llm.router import LLMRouter


def test_ollama_client_provider():
    client = OllamaClient(base_url="http://localhost:11434", model="mistral")
    assert client.provider == "local"


def test_openrouter_client_provider():
    client = OpenRouterClient(
        api_key="test_key",
        base_url="https://openrouter.ai/api/v1",
        model="openrouter/elephant-alpha",
    )
    assert client.provider == "cloud"


def test_llm_response_parsing():
    from app.pipeline.verify import VerificationPipeline

    pipeline = VerificationPipeline()
    score, verdict, explanation = pipeline._parse_llm_response(
        '{"truth_score": 0.85, "verdict": "Likely True", "explanation": "Test reasoning."}'
    )
    assert score == 0.85
    assert verdict == "Likely True"
    assert explanation == "Test reasoning."


def test_llm_response_parsing_fallback():
    from app.pipeline.verify import VerificationPipeline

    pipeline = VerificationPipeline()
    score, verdict, explanation = pipeline._parse_llm_response("Invalid response")
    assert score == 0.5
    assert verdict == "Uncertain"
    assert explanation == "Invalid response"
