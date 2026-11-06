"""Agent-to-Agent (A2A) Service Mesh & Registry.

Provides dynamic agent registration, heartbeat monitoring, capability-based
discovery, load balancing, and an asynchronous message bus with topic pub/sub
and point-to-point agent routing.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
import uuid
from enum import Enum
from typing import Any, Callable, Coroutine, Dict, List, Optional
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class AgentStatus(str, Enum):
    ONLINE = "online"
    BUSY = "busy"
    DRAINING = "draining"
    OFFLINE = "offline"


class RoutingStrategy(str, Enum):
    ROUND_ROBIN = "round_robin"
    LEAST_LOADED = "least_loaded"
    RANDOM = "random"


class AgentNode(BaseModel):
    """Represents an autonomous AI agent registered within the service mesh."""

    agent_id: str = Field(description="Unique agent identifier")
    name: str = Field(description="Human-readable name of the agent")
    capabilities: List[str] = Field(default_factory=list, description="Capabilities provided, e.g. 'code_review', 'sql'")
    tools: List[str] = Field(default_factory=list, description="Tools exposed by the agent, e.g. 'python_repl', 'web_search'")
    endpoint: Optional[str] = Field(default=None, description="Direct HTTP or RPC endpoint URL if remote")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary custom agent metadata")
    status: AgentStatus = Field(default=AgentStatus.ONLINE, description="Current operational state")
    current_load: float = Field(default=0.0, ge=0.0, description="Normalized agent workload or active concurrent task count")
    last_heartbeat: float = Field(default_factory=time.time, description="Unix timestamp of latest heartbeat")
    heartbeat_ttl: float = Field(default=30.0, description="Maximum seconds allowed between heartbeats before marked offline")

    def is_alive(self) -> bool:
        """Check if agent is currently reachable and not expired."""
        if self.status == AgentStatus.OFFLINE:
            return False
        return (time.time() - self.last_heartbeat) <= self.heartbeat_ttl


class MessageEnvelope(BaseModel):
    """Standardized asynchronous message envelope for inter-agent communication."""

    message_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    trace_id: Optional[str] = None
    sender_id: str
    target_id: Optional[str] = None  # None indicates broadcast or topic publish
    topic: Optional[str] = None
    payload: Dict[str, Any] = Field(default_factory=dict)
    correlation_id: Optional[str] = None
    timestamp: float = Field(default_factory=time.time)


class AgentRegistry:
    """Thread-safe and async-friendly in-memory registry of all active agents."""

    def __init__(self, stale_check_interval: float = 60.0):
        self._agents: Dict[str, AgentNode] = {}
        self._rr_counters: Dict[str, int] = {}
        self.stale_check_interval = stale_check_interval

    def register(self, node: AgentNode) -> AgentNode:
        """Register or update an agent node in the mesh."""
        node.last_heartbeat = time.time()
        self._agents[node.agent_id] = node
        logger.info(f"Registered agent node '{node.agent_id}' ({node.name})")
        return node

    def deregister(self, agent_id: str) -> bool:
        """Remove an agent from the active registry."""
        if agent_id in self._agents:
            del self._agents[agent_id]
            logger.info(f"Deregistered agent node '{agent_id}'")
            return True
        return False

    def heartbeat(self, agent_id: str, current_load: Optional[float] = None, status: Optional[AgentStatus] = None) -> bool:
        """Process heartbeat from an agent, refreshing its TTL and optional workload."""
        agent = self._agents.get(agent_id)
        if not agent:
            return False
        agent.last_heartbeat = time.time()
        if current_load is not None:
            agent.current_load = max(0.0, current_load)
        if status is not None:
            agent.status = status
        elif agent.status == AgentStatus.OFFLINE:
            agent.status = AgentStatus.ONLINE
        return True

    def get_agent(self, agent_id: str) -> Optional[AgentNode]:
        """Fetch agent by identifier."""
        return self._agents.get(agent_id)

    def list_agents(
        self,
        alive_only: bool = True,
        capability: Optional[str] = None,
        tool: Optional[str] = None,
    ) -> List[AgentNode]:
        """List registered agents with optional filters."""
        candidates = list(self._agents.values())
        if alive_only:
            candidates = [a for a in candidates if a.is_alive()]
        if capability:
            candidates = [a for a in candidates if capability in a.capabilities]
        if tool:
            candidates = [a for a in candidates if tool in a.tools]
        return candidates

    def discover(
        self,
        capability: Optional[str] = None,
        tool: Optional[str] = None,
        strategy: RoutingStrategy = RoutingStrategy.LEAST_LOADED,
    ) -> Optional[AgentNode]:
        """Discover an optimal alive agent matching capability or tool constraints."""
        candidates = self.list_agents(alive_only=True, capability=capability, tool=tool)
        if not candidates:
            return None

        if strategy == RoutingStrategy.LEAST_LOADED:
            return min(candidates, key=lambda a: a.current_load)

        if strategy == RoutingStrategy.RANDOM:
            return random.choice(candidates)

        if strategy == RoutingStrategy.ROUND_ROBIN:
            key = f"cap:{capability}|tool:{tool}"
            idx = self._rr_counters.get(key, 0)
            chosen = candidates[idx % len(candidates)]
            self._rr_counters[key] = idx + 1
            return chosen

        return candidates[0]

    def evict_stale_agents(self) -> int:
        """Mark agents exceeding heartbeat TTL as OFFLINE."""
        evicted = 0
        now = time.time()
        for agent in self._agents.values():
            if agent.status != AgentStatus.OFFLINE and (now - agent.last_heartbeat) > agent.heartbeat_ttl:
                agent.status = AgentStatus.OFFLINE
                evicted += 1
        return evicted


class AgentMessageBus:
    """Asynchronous message bus enabling pub/sub topics and point-to-point mailboxes."""

    def __init__(self, registry: AgentRegistry):
        self.registry = registry
        # Mailbox queues for point-to-point delivery: agent_id -> asyncio.Queue
        self._mailboxes: Dict[str, asyncio.Queue[MessageEnvelope]] = {}
        # Topic subscribers: topic -> list of callbacks
        self._topic_subscribers: Dict[str, List[Callable[[MessageEnvelope], Coroutine[Any, Any, None]]]] = {}

    def _ensure_mailbox(self, agent_id: str) -> asyncio.Queue[MessageEnvelope]:
        if agent_id not in self._mailboxes:
            self._mailboxes[agent_id] = asyncio.Queue(maxsize=1000)
        return self._mailboxes[agent_id]

    async def send_direct(
        self,
        sender_id: str,
        target_id: str,
        payload: Dict[str, Any],
        correlation_id: Optional[str] = None,
        trace_id: Optional[str] = None,
    ) -> MessageEnvelope:
        """Deliver a direct message into a target agent's mailbox."""
        target = self.registry.get_agent(target_id)
        if not target or not target.is_alive():
            raise LookupError(f"Target agent '{target_id}' is unreachable or offline")

        envelope = MessageEnvelope(
            sender_id=sender_id,
            target_id=target_id,
            payload=payload,
            correlation_id=correlation_id,
            trace_id=trace_id,
        )

        mailbox = self._ensure_mailbox(target_id)
        try:
            mailbox.put_nowait(envelope)
        except asyncio.QueueFull:
            raise RuntimeError(f"Mailbox for agent '{target_id}' is full")

        return envelope

    def subscribe(self, topic: str, callback: Callable[[MessageEnvelope], Coroutine[Any, Any, None]]) -> None:
        """Subscribe an async callback to a topic."""
        if topic not in self._topic_subscribers:
            self._topic_subscribers[topic] = []
        self._topic_subscribers[topic].append(callback)

    def unsubscribe(self, topic: str, callback: Callable[[MessageEnvelope], Coroutine[Any, Any, None]]) -> bool:
        """Unsubscribe a callback from a topic."""
        if topic in self._topic_subscribers and callback in self._topic_subscribers[topic]:
            self._topic_subscribers[topic].remove(callback)
            return True
        return False

    async def publish(
        self,
        sender_id: str,
        topic: str,
        payload: Dict[str, Any],
        trace_id: Optional[str] = None,
    ) -> int:
        """Publish a message to all subscribers of a topic."""
        envelope = MessageEnvelope(
            sender_id=sender_id,
            topic=topic,
            payload=payload,
            trace_id=trace_id,
        )

        subscribers = self._topic_subscribers.get(topic, [])
        delivered = 0
        for callback in subscribers:
            try:
                # Dispatch concurrently without blocking publisher
                asyncio.create_task(callback(envelope))
                delivered += 1
            except Exception as e:
                logger.error(f"Error dispatching topic '{topic}' to callback: {e}")

        return delivered

    async def receive(self, agent_id: str, timeout: Optional[float] = None) -> Optional[MessageEnvelope]:
        """Receive the next message from an agent's mailbox."""
        mailbox = self._ensure_mailbox(agent_id)
        try:
            if timeout is not None:
                return await asyncio.wait_for(mailbox.get(), timeout=timeout)
            return await mailbox.get()
        except asyncio.TimeoutError:
            return None
