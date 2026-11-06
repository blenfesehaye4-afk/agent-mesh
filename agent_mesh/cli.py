"""Rich CLI interface for AgentMesh gateway management, performance benchmarks, and mesh operations."""

import argparse
import asyncio
import time
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .budget import BudgetLedger
from .gateway import AgentMeshGateway
from .mesh import AgentNode, AgentRegistry, AgentStatus
from .models import ChatCompletionRequest, ChatMessage, Role
from .tool_governor import ToolGovernor

console = Console()


async def run_benchmark(iterations: int = 100):
    console.print(Panel(f"[bold cyan]AgentMesh Gateway Benchmark[/bold cyan]\nTotal Queries: [yellow]{iterations}[/yellow]"))

    gw = AgentMeshGateway()

    # Pre-populate some knowledge
    await gw.complete(ChatCompletionRequest(
        model="gpt-4o",
        messages=[ChatMessage(role=Role.USER, content="How does distributed consensus work in Raft?")],
    ))

    # Test queries with semantically similar wording
    test_queries = [
        "How does distributed consensus work in Raft?",
        "Explain the Raft distributed consensus algorithm.",
        "What is Raft consensus mechanism?",
        "What is the capital of France?",
        "Tell me about the capital city of France.",
    ]

    start = time.perf_counter()
    for i in range(iterations):
        q = test_queries[i % len(test_queries)]
        await gw.complete(ChatCompletionRequest(
            model="gpt-4o",
            messages=[ChatMessage(role=Role.USER, content=q)],
        ))

    duration = time.perf_counter() - start
    qps = iterations / duration

    stats = gw.cache.stats()
    m = gw.metrics

    table = Table(title="⚡ Gateway Performance & Semantic Cache Results")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="yellow")

    table.add_row("Total Requests", f"{iterations:,}")
    table.add_row("Execution Time", f"{duration:.3f} s")
    table.add_row("Throughput", f"{qps:,.0f} req/sec")
    table.add_row("Cache Hits", f"{m.cache_hits} ({stats['hit_ratio'] * 100:.1f}%)")
    table.add_row("Cache Misses", str(m.cache_misses))
    table.add_row("Tokens Saved", f"{m.tokens_saved:,}")

    console.print(table)


async def run_mesh_demo():
    console.print(Panel("[bold cyan]AgentMesh A2A Mesh & Governance Demo[/bold cyan]"))
    gw = AgentMeshGateway()

    # Register sample agents
    gw.registry.register(AgentNode(
        agent_id="agent-coder-1",
        name="Python Coder Agent",
        capabilities=["python", "refactor"],
        tools=["python_repl", "git"],
        current_load=0.2,
    ))
    gw.registry.register(AgentNode(
        agent_id="agent-search-1",
        name="Web Researcher Agent",
        capabilities=["research", "web_search"],
        tools=["bing_search", "fetch_url"],
        current_load=0.1,
    ))

    # Capability discovery
    coder = gw.registry.discover(capability="python")
    researcher = gw.registry.discover(tool="bing_search")

    table = Table(title="🌐 Active Mesh Agents")
    table.add_column("Agent ID", style="cyan")
    table.add_column("Name", style="magenta")
    table.add_column("Capabilities", style="green")
    table.add_column("Tools", style="yellow")
    table.add_column("Status", style="blue")

    for agent in gw.registry.list_agents():
        table.add_row(agent.agent_id, agent.name, ", ".join(agent.capabilities), ", ".join(agent.tools), agent.status.value)
    console.print(table)

    # HITL Tool Governor Evaluation
    gov = ToolGovernor()
    eval1 = gov.evaluate("agent-coder-1", "bash_exec", {"cmd": "rm -rf /tmp"})
    eval2 = gov.evaluate("agent-search-1", "fetch_url", {"url": "https://example.com"})

    gov_table = Table(title="🛡️ HITL Tool Governance Sandbox")
    gov_table.add_column("Agent", style="cyan")
    gov_table.add_column("Proposed Tool", style="magenta")
    gov_table.add_column("Risk Level", style="yellow")
    gov_table.add_column("Reason / Action", style="white")

    gov_table.add_row("agent-coder-1", "bash_exec", eval1[0].value, eval1[1])
    gov_table.add_row("agent-search-1", "fetch_url", eval2[0].value, eval2[1])
    console.print(gov_table)


def main():
    parser = argparse.ArgumentParser(
        prog="agent-mesh",
        description="🧠 AgentMesh: AI Agent Gateway, Service Mesh & Governance Proxy CLI.",
    )
    subparsers = parser.add_subparsers(dest="command")

    # Serve
    srv = subparsers.add_parser("serve", help="Start FastAPI gateway server")
    srv.add_argument("--host", default="0.0.0.0")
    srv.add_argument("--port", type=int, default=8000)

    # Bench
    bench = subparsers.add_parser("bench", help="Run semantic caching latency benchmark")
    bench.add_argument("--n", type=int, default=100)

    # Demo
    subparsers.add_parser("demo", help="Demonstrate Agent Mesh discovery and tool governance")

    args = parser.parse_args()

    if args.command == "serve":
        import uvicorn
        console.print(f"[bold green]Starting AgentMesh Gateway on {args.host}:{args.port}[/bold green]")
        uvicorn.run("agent_mesh.server:app", host=args.host, port=args.port, reload=False)
    elif args.command == "bench":
        asyncio.run(run_benchmark(iterations=args.n))
    elif args.command == "demo":
        asyncio.run(run_mesh_demo())
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
