"""Rich CLI interface for AgentMesh gateway management and performance benchmarks."""

import argparse
import asyncio
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .gateway import AgentMeshGateway
from .models import ChatCompletionRequest, ChatMessage, Role

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

    import time
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


def main():
    parser = argparse.ArgumentParser(
        prog="agent-mesh",
        description="🧠 AgentMesh: AI Agent Gateway, Semantic Vector Cache & Governance Proxy CLI.",
    )
    subparsers = parser.add_subparsers(dest="command")

    # Serve
    srv = subparsers.add_parser("serve", help="Start FastAPI gateway server")
    srv.add_argument("--host", default="0.0.0.0")
    srv.add_argument("--port", type=int, default=8000)

    # Bench
    bench = subparsers.add_parser("bench", help="Run semantic caching latency benchmark")
    bench.add_argument("--n", type=int, default=100)

    args = parser.parse_args()

    if args.command == "serve":
        import uvicorn
        console.print(f"[bold green]Starting AgentMesh Gateway on {args.host}:{args.port}[/bold green]")
        uvicorn.run("agent_mesh.server:app", host=args.host, port=args.port, reload=False)
    elif args.command == "bench":
        asyncio.run(run_benchmark(iterations=args.n))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
