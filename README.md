# 🧠 AgentMesh

[![CI](https://github.com/blenfesehaye4-afk/agent-mesh/actions/workflows/ci.yml/badge.svg)](https://github.com/blenfesehaye4-afk/agent-mesh/actions/workflows/ci.yml)
[![Python Version](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

> **High-performance AI agent gateway, semantic vector cache, multi-provider circuit breaker & SSE streaming proxy.**

AgentMesh is an enterprise-grade AI proxy and governance layer for LLMs and autonomous agents. It sits between client applications and AI inference providers to slash token costs via semantic caching, enforce data privacy via automatic PII masking, prevent prompt injection jailbreaks, provide resilient multi-provider failover, stream responses via Server-Sent Events (SSE), and validate structured tool outputs against JSON schemas.

---

## 🌟 What's New in v0.2.0

- 🔌 **Server-Sent Events (SSE) Streaming** ([`agent_mesh/streaming.py`](file:///home/moaa/Desktop/my%20programs/bibi%20github/agent-mesh/agent_mesh/streaming.py)): Native streaming support via `stream: true` on `/v1/chat/completions` with incremental chunk delivery.
- ⚡ **Circuit Breaker & Multi-Provider Router** ([`agent_mesh/router.py`](file:///home/moaa/Desktop/my%20programs/bibi%20github/agent-mesh/agent_mesh/router.py)): Resilient failover across model providers (`primary` -> `secondary`). Automatically trips open upon consecutive upstream errors to protect downstream systems.
- 📋 **Structured Tool Output Schema Validation** ([`agent_mesh/schema_validator.py`](file:///home/moaa/Desktop/my%20programs/bibi%20github/agent-mesh/agent_mesh/schema_validator.py)): Enforces JSON schema constraints and data types on agent function arguments and structured responses.

---

## 🏗️ Architecture

```
[ Client / AI Agents ]
          │
          ├── 1. POST /v1/chat/completions (stream: bool)
          ▼
   ┌────────────────────────────────────────────────────────┐
   │ AgentMesh Gateway                                      │
   │                                                        │
   │  [ 1. Rate Limiter ]    ➔ Token-bucket per tenant      │
   │  [ 2. Guardrails ]      ➔ Redact Emails, Keys, SSN, CC │
   │                           Block Prompt Injections      │
   │  [ 3. Semantic Cache]   ➔ TF-IDF & Cosine Similarity   │
   │  [ 4. Circuit Breaker]  ➔ Multi-provider cascade router│
   │  [ 5. Schema Validator] ➔ JSON schema type safety      │
   └──────────┬─────────────────────────────┬───────────────┘
              │ (Cache Hit)                 │ (Cache Miss)
              ▼                             ▼
       Instant Response            [ Provider Pool ]
       (0 tokens billed)           OpenAI / Anthropic / Ollama
```

---

## 💻 Python Quickstart (Streaming & Guardrails)

```python
import asyncio
from agent_mesh import AgentMeshGateway, ChatCompletionRequest, ChatMessage, Role

async def main():
    gw = AgentMeshGateway()

    req = ChatCompletionRequest(
        model="gpt-4o",
        messages=[ChatMessage(role=Role.USER, content="Hello, analyze this data")],
        stream=False,
    )

    resp = await gw.complete(req)
    print("Response:", resp.choices[0].message.content)

asyncio.run(main())
```

---

## 🖥️ Command-Line Interface (CLI)

```bash
# Start FastAPI gateway server
agent-mesh serve --host 0.0.0.0 --port 8000

# Run high-concurrency semantic caching benchmark
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
