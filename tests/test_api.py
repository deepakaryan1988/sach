import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

from app.main import app
from app.models.responses import Source

client = TestClient(app)


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_verify_endpoint_missing_query():
    response = client.post("/verify", json={})
    assert response.status_code == 422


def test_verify_endpoint_valid_request():
    mock_response = {
        "query": "The Earth is round.",
        "truth_score": 0.95,
        "verdict": "Likely True",
        "sources": [Source(title="NASA", content="Earth is round")],
        "explanation": "Confirmed by NASA.",
        "model_used": "local",
        "latency_ms": 123.45,
    }

    with patch("app.api.routes.pipeline.verify", new_callable=AsyncMock) as mock_verify:
        from app.models.responses import VerifyResponse

        mock_verify.return_value = VerifyResponse(**mock_response)

        response = client.post("/verify", json={"query": "The Earth is round."})
        assert response.status_code == 200
        data = response.json()
        assert data["query"] == "The Earth is round."
        assert data["truth_score"] == 0.95
        assert data["verdict"] == "Likely True"
        assert data["model_used"] == "local"
