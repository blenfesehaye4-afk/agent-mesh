import asyncio
import pytest
from agent_mesh.mesh import (
    AgentMessageBus,
    AgentNode,
    AgentRegistry,
    AgentStatus,
    RoutingStrategy,
)


def test_agent_registration_and_status():
    reg = AgentRegistry()
    node = AgentNode(
        agent_id="agent-01",
        name="Reviewer",
        capabilities=["code_review"],
        tools=["git_diff"],
        current_load=0.1,
    )
    reg.register(node)

    assert reg.get_agent("agent-01") is not None
    assert reg.get_agent("agent-01").is_alive() is True

    # Heartbeat
    assert reg.heartbeat("agent-01", current_load=0.5) is True
    assert reg.get_agent("agent-01").current_load == 0.5


def test_agent_discovery_strategies():
    reg = AgentRegistry()
    reg.register(AgentNode(
        agent_id="worker-heavy",
        name="Heavy Worker",
        capabilities=["compute"],
        current_load=0.9,
    ))
    reg.register(AgentNode(
        agent_id="worker-light",
        name="Light Worker",
        capabilities=["compute"],
        current_load=0.1,
    ))

    # Least loaded strategy should pick worker-light
    selected = reg.discover(capability="compute", strategy=RoutingStrategy.LEAST_LOADED)
    assert selected is not None
    assert selected.agent_id == "worker-light"

    # Round robin strategy
    rr1 = reg.discover(capability="compute", strategy=RoutingStrategy.ROUND_ROBIN)
    rr2 = reg.discover(capability="compute", strategy=RoutingStrategy.ROUND_ROBIN)
    assert rr1 is not None and rr2 is not None
    assert rr1.agent_id != rr2.agent_id


def test_agent_staleness_and_eviction():
    reg = AgentRegistry()
    node = AgentNode(
        agent_id="stale-worker",
        name="Stale Worker",
        capabilities=["compute"],
        heartbeat_ttl=0.01,
    )
    reg.register(node)
    # Simulate past heartbeat
    node.last_heartbeat = 100.0

    evicted = reg.evict_stale_agents()
    assert evicted == 1
    assert node.status == AgentStatus.OFFLINE
    assert node.is_alive() is False


@pytest.mark.asyncio
async def test_message_bus_point_to_point():
    reg = AgentRegistry()
    bus = AgentMessageBus(reg)

    reg.register(AgentNode(agent_id="sender-agent", name="Sender"))
    reg.register(AgentNode(agent_id="receiver-agent", name="Receiver"))

    # Send direct message
    env = await bus.send_direct(
        sender_id="sender-agent",
        target_id="receiver-agent",
        payload={"instruction": "summarize_document"},
        correlation_id="corr-123",
    )
    assert env.message_id is not None
    assert env.correlation_id == "corr-123"

    # Receive message
    received = await bus.receive("receiver-agent", timeout=1.0)
    assert received is not None
    assert received.payload["instruction"] == "summarize_document"
    assert received.sender_id == "sender-agent"


@pytest.mark.asyncio
async def test_message_bus_topic_pubsub():
    reg = AgentRegistry()
    bus = AgentMessageBus(reg)

    delivered_messages = []

    async def topic_handler(msg):
        delivered_messages.append(msg)

    bus.subscribe("market_updates", topic_handler)

    count = await bus.publish(
        sender_id="feed_agent",
        topic="market_updates",
        payload={"symbol": "NVDA", "price": 140.5},
    )
    assert count == 1

    # Allow async task to complete
    await asyncio.sleep(0.05)
    assert len(delivered_messages) == 1
    assert delivered_messages[0].payload["symbol"] == "NVDA"
