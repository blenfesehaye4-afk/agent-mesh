"""Human-in-the-Loop (HITL) & Tool Execution Sandbox Governance.

Evaluates AI agent tool calls against a permission matrix, classifies tool risk,
intercepts dangerous operations (e.g. bash execution, data deletion, financial transactions),
and suspends agent execution until a human administrator approves or rejects via ticket.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
import uuid
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class PermissionLevel(str, Enum):
    SAFE = "safe"              # Auto-executed, no interruption
    ELEVATED = "elevated"      # Allowed, but logged and tagged in telemetry
    HIGH_RISK = "high_risk"    # Blocked until explicit human approval ticket resolves


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class ApprovalTicket(BaseModel):
    """An interception ticket generated when an agent attempts a HIGH_RISK tool action."""

    ticket_id: str = Field(default_factory=lambda: f"tkt-{uuid.uuid4().hex[:8]}")
    agent_id: str
    tool_name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)
    permission_level: PermissionLevel = PermissionLevel.HIGH_RISK
    risk_reason: str = "High-risk tool operation requires human-in-the-loop authorization"
    status: ApprovalStatus = ApprovalStatus.PENDING
    created_at: float = Field(default_factory=time.time)
    resolved_at: Optional[float] = None
    resolved_by: Optional[str] = None
    rejection_reason: Optional[str] = None


class ToolGovernor:
    """Enterprise policy engine and HITL approval queue for agent tool executions."""

    def __init__(self):
        # Patterns for tool classification: list of (regex_pattern, PermissionLevel, reason)
        self._policies: List[Tuple[re.Pattern, PermissionLevel, str]] = []
        self._tickets: Dict[str, ApprovalTicket] = {}
        self._events: Dict[str, asyncio.Event] = {}

        # Register robust default safety policies
        self.register_policy(
            r"(?i)(bash|sh|exec|terminal|command|powershell|subprocess|eval)",
            PermissionLevel.HIGH_RISK,
            "Arbitrary shell/command execution detected",
        )
        self.register_policy(
            r"(?i)(delete|drop|truncate|rm|destroy|format)",
            PermissionLevel.HIGH_RISK,
            "Destructive resource modification or deletion detected",
        )
        self.register_policy(
            r"(?i)(transfer|payment|invoice|credit_card|withdraw|send_money)",
            PermissionLevel.HIGH_RISK,
            "Financial transaction capability detected",
        )
        self.register_policy(
            r"(?i)(send_email|post_tweet|webhook|slack_post|write_file)",
            PermissionLevel.ELEVATED,
            "External side-effect or data modification",
        )

    def register_policy(self, pattern: str, level: PermissionLevel, reason: str) -> None:
        """Register a regex policy pattern for matching tool names."""
        compiled = re.compile(pattern)
        self._policies.append((compiled, level, reason))

    def evaluate(self, agent_id: str, tool_name: str, arguments: Optional[Dict[str, Any]] = None) -> Tuple[PermissionLevel, str]:
        """Classify a proposed tool execution against registered policies."""
        args = arguments or {}

        # 1. Check policies in order
        for regex, level, reason in self._policies:
            if regex.search(tool_name):
                return level, f"Policy match [{regex.pattern}]: {reason}"

        # 2. Inspect argument keys or values for dangerous patterns (e.g. rm -rf or DROP TABLE)
        arg_str = str(args).lower()
        if "rm -rf" in arg_str or "drop table" in arg_str or "truncate table" in arg_str:
            return PermissionLevel.HIGH_RISK, "Dangerous argument payload detected"

        return PermissionLevel.SAFE, "Operation permitted under default policy"

    def request_approval(
        self,
        agent_id: str,
        tool_name: str,
        arguments: Dict[str, Any],
        reason: str,
    ) -> ApprovalTicket:
        """Create a pending approval ticket and register its resolution event."""
        ticket = ApprovalTicket(
            agent_id=agent_id,
            tool_name=tool_name,
            arguments=arguments,
            risk_reason=reason,
            status=ApprovalStatus.PENDING,
        )
        self._tickets[ticket.ticket_id] = ticket
        self._events[ticket.ticket_id] = asyncio.Event()
        logger.warning(
            f"Generated HITL ticket '{ticket.ticket_id}' for agent '{agent_id}' invoking '{tool_name}' ({reason})"
        )
        return ticket

    async def wait_for_decision(self, ticket_id: str, timeout: float = 30.0) -> ApprovalTicket:
        """Asynchronously wait for human operator to approve or reject the ticket."""
        ticket = self._tickets.get(ticket_id)
        if not ticket:
            raise KeyError(f"Approval ticket '{ticket_id}' does not exist")

        event = self._events.get(ticket_id)
        if not event:
            return ticket

        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            ticket.status = ApprovalStatus.EXPIRED
            ticket.resolved_at = time.time()
            ticket.rejection_reason = f"Approval timed out after {timeout} seconds"
            logger.info(f"Ticket '{ticket_id}' expired due to timeout")

        return ticket

    def approve(self, ticket_id: str, approver: str = "admin") -> bool:
        """Approve a pending ticket, notifying waiting async tasks."""
        ticket = self._tickets.get(ticket_id)
        if not ticket or ticket.status != ApprovalStatus.PENDING:
            return False

        ticket.status = ApprovalStatus.APPROVED
        ticket.resolved_at = time.time()
        ticket.resolved_by = approver
        logger.info(f"Ticket '{ticket_id}' APPROVED by '{approver}'")

        if ticket_id in self._events:
            self._events[ticket_id].set()
        return True

    def reject(self, ticket_id: str, reason: str = "Action rejected by operator", approver: str = "admin") -> bool:
        """Reject a pending ticket, notifying waiting async tasks."""
        ticket = self._tickets.get(ticket_id)
        if not ticket or ticket.status != ApprovalStatus.PENDING:
            return False

        ticket.status = ApprovalStatus.REJECTED
        ticket.resolved_at = time.time()
        ticket.resolved_by = approver
        ticket.rejection_reason = reason
        logger.info(f"Ticket '{ticket_id}' REJECTED by '{approver}': {reason}")

        if ticket_id in self._events:
            self._events[ticket_id].set()
        return True

    def get_ticket(self, ticket_id: str) -> Optional[ApprovalTicket]:
        return self._tickets.get(ticket_id)

    def list_tickets(self, status: Optional[ApprovalStatus] = None) -> List[ApprovalTicket]:
        tickets = list(self._tickets.values())
        if status:
            return [t for t in tickets if t.status == status]
        return sorted(tickets, key=lambda t: t.created_at, reverse=True)
