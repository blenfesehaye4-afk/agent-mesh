import pytest
from fastapi.testclient import TestClient
from agent_mesh.server import app

client = TestClient(app)


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "service": "agent-mesh", "version": "0.2.0"}


def test_chat_completions_endpoint():
    payload = {
        "model": "gpt-4o",
        "messages": [
            {"role": "user", "content": "How do embeddings work in vector search?"}
        ]
    }
    response = client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "choices" in data
    assert len(data["choices"]) > 0
    assert data["choices"][0]["message"]["role"] == "assistant"


def test_metrics_endpoint():
    response = client.get("/v1/metrics")
    assert response.status_code == 200
    assert "agentmesh_requests_total" in response.text
