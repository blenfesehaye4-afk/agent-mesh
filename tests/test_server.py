import pytest
from fastapi.testclient import TestClient
from agent_mesh import __version__
from agent_mesh.server import app

client = TestClient(app)


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "service": "agent-mesh", "version": __version__}


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
    assert "trace_id" in data
    assert data["cost_usd"] is not None


def test_metrics_endpoint():
    response = client.get("/v1/metrics")
    assert response.status_code == 200
    assert "agentmesh_requests_total" in response.text
    assert "agentmesh_spend_usd_total" in response.text
    assert "agentmesh_active_agents_total" in response.text


def test_mesh_agent_registration_and_discovery():
    agent_payload = {
        "agent_id": "test-analyst-1",
        "name": "Data Analyst Agent",
        "capabilities": ["data_analysis", "sql"],
        "tools": ["query_postgres"],
        "current_load": 0.15,
    }
    # Register
    res = client.post("/v1/mesh/agents", json=agent_payload)
    assert res.status_code == 200
    data = res.json()
    assert data["agent_id"] == "test-analyst-1"

    # List & Discover
    list_res = client.get("/v1/mesh/agents?capability=data_analysis")
    assert list_res.status_code == 200
    agents = list_res.json()
    assert any(a["agent_id"] == "test-analyst-1" for a in agents)

    # Heartbeat
    hb_res = client.post("/v1/mesh/agents/test-analyst-1/heartbeat", json={"current_load": 0.25})
    assert hb_res.status_code == 200
    assert hb_res.json()["status"] == "acknowledged"


def test_mesh_messaging():
    # Register target agent
    client.post("/v1/mesh/agents", json={
        "agent_id": "target-worker",
        "name": "Target Worker",
        "capabilities": ["worker"],
    })

    # Send direct message
    msg_payload = {
        "sender_id": "coordinator",
        "target_id": "target-worker",
        "payload": {"task": "process_batch_77"},
    }
    msg_res = client.post("/v1/mesh/messages/direct", json=msg_payload)
    assert msg_res.status_code == 200
    envelope = msg_res.json()
    assert envelope["sender_id"] == "coordinator"
    assert envelope["payload"]["task"] == "process_batch_77"

    # Read from mailbox
    inbox_res = client.get("/v1/mesh/agents/target-worker/mailbox?timeout=1.0")
    assert inbox_res.status_code == 200
    rcv_envelope = inbox_res.json()
    assert rcv_envelope["payload"]["task"] == "process_batch_77"


def test_budget_governance_api():
    # Set quota
    set_res = client.post("/v1/governance/budget", json={
        "tenant_id": "team-ml",
        "max_budget_usd": 50.0,
        "soft_limit_usd": 40.0,
        "downgrade_on_soft_limit": True,
        "fallback_model": "gpt-4o-mini",
    })
    assert set_res.status_code == 200
    data = set_res.json()
    assert data["max_budget_usd"] == 50.0

    # Get budget summary
    get_res = client.get("/v1/governance/budget?tenant_id=team-ml")
    assert get_res.status_code == 200
    assert get_res.json()["tenant_id"] == "team-ml"


def test_hitl_tool_governance_api():
    # Evaluate tool
    eval_res = client.post("/v1/governance/tools/evaluate", json={
        "agent_id": "agent-x",
        "tool_name": "bash_terminal",
        "arguments": {"cmd": "ls -la"},
    })
    assert eval_res.status_code == 200
    eval_data = eval_res.json()
    assert eval_data["permission_level"] == "high_risk"
    assert eval_data["requires_hitl"] is True
