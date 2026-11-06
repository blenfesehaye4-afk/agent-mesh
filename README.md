# 🧠 AgentMesh

[![CI](https://github.com/blenfesehaye4-afk/agent-mesh/actions/workflows/ci.yml/badge.svg)](https://github.com/blenfesehaye4-afk/agent-mesh/actions/workflows/ci.yml)
[![Python Version](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

> **High-performance AI agent gateway, semantic vector cache, PII guardrails & proxy.**

AgentMesh is an enterprise-grade AI proxy and governance layer for LLMs and autonomous agents. It sits between client applications and AI inference providers to slash token costs via semantic caching, enforce data privacy via automatic PII masking, prevent prompt injection jailbreaks, and export Prometheus telemetry.

---

## 🌟 Key Architecture & Features

```
[ Client / AI Agents ]
          │
          ├── 1. POST /v1/chat/completions
          ▼
   ┌────────────────────────────────────────────────────────┐
   │ AgentMesh Gateway                                      │
   │                                                        │
   │  [ 1. Rate Limiter ] ➔ Token-bucket per tenant         │
   │  [ 2. Guardrails ]   ➔ Redact Emails, Keys, SSN, CC    │
   │                        Block Prompt Injections         │
   │  [ 3. Semantic Cache]➔ TF-IDF & Cosine Similarity      │
   │                        Exact match O(1)                │
   └──────────┬─────────────────────────────┬───────────────┘
              │ (Cache Hit)                 │ (Cache Miss)
              ▼                             ▼
       Instant Response            [ Upstream LLM ]
       (0 tokens billed)           OpenAI / Anthropic / Local
```

- ⚡ **Semantic Vector Cache**: In-memory cosine similarity cache for semantically equivalent prompts—cutting inference costs and latency.
- 🛡️ **PII Masking & Privacy Guardrails**: Auto-redacts email addresses, OpenAI/GitHub API keys (`sk-...`, `ghp_...`), Credit Cards, SSNs, and IPv4 addresses.
- 🚫 **Prompt Injection Defense**: Heuristic detection of jailbreak phrases (`ignore previous instructions`, `bypass guardrails`, `DAN`).
- ⏱️ **Token-Bucket Rate Limiter**: Enforces dynamic request and token throughput budgets per tenant.
- 📈 **Prometheus Observability**: Native `/v1/metrics` exposition (`agentmesh_requests_total`, `agentmesh_cache_hits_total`, `agentmesh_tokens_saved_total`).
- 🔌 **OpenAI Compatible**: Drop-in compatible with standard OpenAI SDKs and LangChain/LlamaIndex agents.

---

## 📦 Installation

```bash
pip install agent-mesh
```

Or install from source in development mode:

```bash
git clone https://github.com/blenfesehaye4-afk/agent-mesh.git
cd agent-mesh
pip install -e .[dev]
```

---

## 💻 Python Quickstart (Embeddable Gateway)

```python
import asyncio
from agent_mesh import AgentMeshGateway, ChatCompletionRequest, ChatMessage, Role

async def main():
    gateway = AgentMeshGateway()

    # Query with PII
    req = ChatCompletionRequest(
        model="gpt-4o",
        messages=[ChatMessage(role=Role.USER, content="Send support to user@example.com using sk-1234567890abcdef1234567890")],
    )

    resp = await gateway.complete(req)
    print(f"PII Redacted: {resp.pii_redacted}")
    print(f"Response: {resp.choices[0].message.content}")

    # Subsequent identical or semantically similar query hits cache!
    cached_resp = await gateway.complete(req)
    print(f"Served from Cache: {cached_resp.cached}")

asyncio.run(main())
```

---

## 🖥️ Command-Line Interface (CLI)

### 1. Launch Gateway Proxy Server
```bash
agent-mesh serve --host 0.0.0.0 --port 8000
```
Open interactive docs: `http://localhost:8000/docs`

### 2. Run Semantic Cache Benchmark
```bash
agent-mesh bench --n 500
```

---

## 🧪 Running Tests

```bash
pytest -v
```

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
