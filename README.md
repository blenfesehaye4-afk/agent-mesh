# 🧠 AgentMesh

[![CI](https://github.com/blenfesehaye4-afk/agent-mesh/actions/workflows/ci.yml/badge.svg)](https://github.com/blenfesehaye4-afk/agent-mesh/actions/workflows/ci.yml)
[![Python Version](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

> **High-performance AI agent gateway, A2A service mesh, distributed tracing, HITL tool governance & dynamic cost routing.**

AgentMesh is an enterprise-grade AI service mesh and governance layer for autonomous agents and LLMs. It sits between client applications, collaborative agent clusters, and inference providers to slash token costs via semantic caching, enforce data privacy via automatic PII masking, prevent prompt injection jailbreaks, provide resilient multi-provider failover, stream responses via Server-Sent Events (SSE), govern tool execution via Human-in-the-Loop (HITL) approval workflows, track multi-agent execution graphs with distributed tracing, and control token spending with dynamic cost routing.

---

## 🌟 What's New in v0.3.0

- 🌐 **Agent-to-Agent (A2A) Service Mesh & Registry** ([`agent_mesh/mesh.py`](file:///home/moaa/Desktop/my%20programs/bibi%20github/agent-mesh/agent_mesh/mesh.py)):
  - Decentralized agent registration with capability/tool tags, heartbeats, and TTL-based stale node eviction.
  - Multi-strategy agent discovery: `LEAST_LOADED`, `ROUND_ROBIN`, and `RANDOM`.
  - Asynchronous event bus supporting point-to-point agent mailboxes and topic-based pub/sub broadcast channels.
- 💰 **Multi-Tenant Budget Ledger & Dynamic Cost Routing** ([`agent_mesh/budget.py`](file:///home/moaa/Desktop/my%20programs/bibi%20github/agent-mesh/agent_mesh/budget.py)):
  - Real-time token consumption ledger and USD financial accounting across model providers.
  - Hard budget ceilings (`BudgetExceededError`) and soft alert thresholds.
  - **Dynamic model downgrading**: Automatically reroutes expensive flagship models (e.g. `gpt-4o`) to lightweight models (e.g. `gpt-4o-mini`) when tenant budgets near consumption limits.
- 🛡️ **Human-in-the-Loop (HITL) & Tool Execution Sandbox** ([`agent_mesh/tool_governor.py`](file:///home/moaa/Desktop/my%20programs/bibi%20github/agent-mesh/agent_mesh/tool_governor.py)):
  - Fine-grained permission matrix: `SAFE` (auto-execute), `ELEVATED` (audited), and `HIGH_RISK` (requires human authorization).
  - Intercepts dangerous operations (shell commands, database drops, money transfers) and issues suspendable approval tickets.
  - Asynchronous resolution with instant event notification upon operator approval/rejection.
- 📡 **Distributed Multi-Agent Tracing & Telemetry** ([`agent_mesh/telemetry.py`](file:///home/moaa/Desktop/my%20programs/bibi%20github/agent-mesh/agent_mesh/telemetry.py)):
  - OpenTelemetry-aligned span lifecycle management and context propagation across asynchronous agent tasks.
  - Hierarchical execution waterfall generation tracking end-to-end multi-agent latency, tool execution chains, and error states.

---

## 🏗️ Architecture

```
[ Client / Autonomous Agents ]
             │
             ├─── 1. POST /v1/chat/completions (stream, tenant, trace)
             ├─── 2. POST /v1/mesh/messages (A2A direct / pub-sub)
             └─── 3. POST /v1/governance/tools/evaluate (HITL sandbox)
             ▼
    ┌─────────────────────────────────────────────────────────────┐
    │ AgentMesh Control Plane & Service Mesh Gateway              │
    │                                                             │
    │  [ Rate Limiter ]      ──▶ Token-bucket per tenant          │
    │  [ Guardrail Engine ]  ──▶ Mask PII & block prompt attacks  │
    │  [ Budget Ledger ]     ──▶ USD caps & dynamic cost router   │
    │  [ Semantic Cache ]    ──▶ TF-IDF & Cosine similarity       │
    │  [ Tool Governor ]     ──▶ HITL tickets for high-risk tools │
    │  [ Agent Registry ]    ──▶ Capability discovery & bus       │
    │  [ Distributed Tracer] ──▶ OpenTelemetry span waterfall     │
    └──────────────┬───────────────────────────────┬──────────────┘
                   │ (Cache Hit)                   │ (Cache Miss)
                   ▼                               ▼
            Instant Response              [ Upstream Providers ]
            (0 tokens billed)             OpenAI / Anthropic / Ollama
```

---

## 💻 Python Quickstart

### 1. Gateway Completions with Distributed Tracing & Budgeting

```python
import asyncio
from agent_mesh import AgentMeshGateway, ChatCompletionRequest, ChatMessage, Role

async def main():
    gw = AgentMeshGateway()

    # Configure tenant budget
    gw.budget.set_quota(
        tenant_id="analytics_team",
        max_budget_usd=100.0,
        soft_limit_usd=80.0,
        downgrade_on_soft_limit=True,
        fallback_model="gpt-4o-mini",
    )

    req = ChatCompletionRequest(
        model="gpt-4o",
        messages=[ChatMessage(role=Role.USER, content="Summarize current GPU architecture trends.")],
    )

    resp = await gw.complete(req, tenant_id="analytics_team")
    print(f"Response: {resp.choices[0].message.content}")
    print(f"Model used: {resp.effective_model} (Downgraded: {resp.downgraded})")
    print(f"Cost: ${resp.cost_usd:.6f} | Trace ID: {resp.trace_id}")

    # Inspect distributed trace waterfall
    waterfall = gw.tracer.export_waterfall(resp.trace_id)
    print(f"Total Trace Latency: {waterfall['total_duration_ms']}ms across {waterfall['span_count']} spans")

asyncio.run(main())
```

### 2. Multi-Agent Discovery & Message Bus (A2A)

```python
import asyncio
from agent_mesh import AgentNode, AgentRegistry, AgentMessageBus, RoutingStrategy

async def main():
    registry = AgentRegistry()
    bus = AgentMessageBus(registry)

    # Register worker agents
    registry.register(AgentNode(
        agent_id="agent-sql-1",
        name="Postgres Analyst",
        capabilities=["data_analysis", "sql"],
        tools=["query_db"],
        current_load=0.1,
    ))

    # Discover least-loaded agent capable of SQL
    target_agent = registry.discover(capability="sql", strategy=RoutingStrategy.LEAST_LOADED)
    print(f"Discovered Agent: {target_agent.name} ({target_agent.agent_id})")

    # Send direct message to agent mailbox
    await bus.send_direct(
        sender_id="coordinator-agent",
        target_id=target_agent.agent_id,
        payload={"query": "SELECT count(*) FROM users;"},
    )

    # Agent receives message from mailbox
    incoming = await bus.receive(target_agent.agent_id, timeout=2.0)
    print(f"Received by {target_agent.agent_id}: {incoming.payload}")

asyncio.run(main())
```

### 3. Human-in-the-Loop (HITL) Tool Sandbox

```python
import asyncio
from agent_mesh import ToolGovernor, PermissionLevel, ApprovalStatus

async def main():
    governor = ToolGovernor()

    # Evaluate tool safety
    level, reason = governor.evaluate("agent-infra", "bash_exec", {"cmd": "rm -rf /var/logs"})
    print(f"Permission: {level.value} -> {reason}")

    if level == PermissionLevel.HIGH_RISK:
        # Generate approval ticket
        ticket = governor.request_approval(
            agent_id="agent-infra",
            tool_name="bash_exec",
            arguments={"cmd": "rm -rf /var/logs"},
            reason=reason,
        )
        print(f"Suspended on Ticket: {ticket.ticket_id} (Status: {ticket.status.value})")

        # Operator approves in admin dashboard / API
        governor.approve(ticket.ticket_id, approver="sec-ops-lead")
        print(f"Resolved Ticket Status: {ticket.status.value} by {ticket.resolved_by}")

asyncio.run(main())
```

---

## 🌐 REST API Endpoints

| Method | Endpoint | Description |
|:---|:---|:---|
| `GET` | `/health` | Service health and active version check |
| `GET` | `/v1/metrics` | Prometheus metrics (requests, spend, agents, cache hits) |
| `POST` | `/v1/chat/completions` | OpenAI-compatible proxy with streaming, tracing & budgeting |
| `GET` | `/v1/cache/stats` | Semantic cache hit rates and memory footprint |
| `POST` | `/v1/mesh/agents` | Register or update autonomous agent node |
| `GET` | `/v1/mesh/agents` | Discover alive agents by capability, tool, or load |
| `DELETE`| `/v1/mesh/agents/{id}` | Deregister agent from mesh |
| `POST` | `/v1/mesh/agents/{id}/heartbeat`| Refresh agent heartbeat and workload state |
| `POST` | `/v1/mesh/messages/direct` | Point-to-point asynchronous agent mailbox delivery |
| `POST` | `/v1/mesh/messages/publish` | Topic broadcast message dispatch |
| `GET` | `/v1/mesh/agents/{id}/mailbox` | Fetch incoming message from agent queue |
| `GET` | `/v1/governance/budget` | Query tenant token ledger and spending limits |
| `POST` | `/v1/governance/budget` | Configure budget caps, soft limits, and fallback models |
| `GET` | `/v1/governance/approvals` | List pending HITL tool authorization tickets |
| `POST` | `/v1/governance/approvals/{id}/approve` | Approve suspended tool execution |
| `POST` | `/v1/governance/approvals/{id}/reject` | Reject suspended tool execution |
| `POST` | `/v1/governance/tools/evaluate` | Evaluate tool safety level against security policies |
| `GET` | `/v1/traces/{trace_id}` | Fetch full hierarchical execution waterfall tree |

---

## 🖥️ Command-Line Interface (CLI)

```bash
# Start FastAPI gateway server with all v0.3.0 mesh endpoints
agent-mesh serve --host 0.0.0.0 --port 8000

# Run high-concurrency semantic caching benchmark
agent-mesh bench --n 500

# Run interactive A2A mesh discovery & HITL governance demo
agent-mesh demo
```

---

## 🧪 Running Tests

```bash
pytest -v
```

All 36 unit and integration tests validate the complete end-to-end functionality including semantic caching, guardrails, circuit breakers, agent discovery, message bus mailboxes, budget ledgers, and HITL tool governance.

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
