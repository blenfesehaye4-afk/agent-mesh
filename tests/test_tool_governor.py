import asyncio
import pytest
from agent_mesh.tool_governor import ApprovalStatus, PermissionLevel, ToolGovernor


def test_tool_governor_evaluation():
    gov = ToolGovernor()

    # Dangerous bash execution -> HIGH_RISK
    level, reason = gov.evaluate("agent-1", "bash_exec", {"cmd": "ls"})
    assert level == PermissionLevel.HIGH_RISK
    assert "shell/command execution" in reason

    # Destructive SQL drop -> HIGH_RISK
    level, reason = gov.evaluate("agent-1", "sql_query", {"query": "DROP TABLE users;"})
    assert level == PermissionLevel.HIGH_RISK

    # Read-only tool -> SAFE
    level, reason = gov.evaluate("agent-1", "read_file", {"path": "/etc/hosts"})
    assert level == PermissionLevel.SAFE


@pytest.mark.asyncio
async def test_tool_governor_approval_workflow():
    gov = ToolGovernor()

    # Create ticket
    ticket = gov.request_approval(
        agent_id="agent-007",
        tool_name="delete_database",
        arguments={"db": "production"},
        reason="Destructive deletion requested",
    )
    assert ticket.status == ApprovalStatus.PENDING

    # Async task approving the ticket after 50ms
    async def approve_later():
        await asyncio.sleep(0.05)
        gov.approve(ticket.ticket_id, approver="security_team")

    asyncio.create_task(approve_later())

    # Wait for decision
    resolved = await gov.wait_for_decision(ticket.ticket_id, timeout=2.0)
    assert resolved.status == ApprovalStatus.APPROVED
    assert resolved.resolved_by == "security_team"


@pytest.mark.asyncio
async def test_tool_governor_rejection_workflow():
    gov = ToolGovernor()

    ticket = gov.request_approval(
        agent_id="agent-008",
        tool_name="transfer_funds",
        arguments={"amount": 10000},
        reason="High-value transfer",
    )

    # Reject ticket
    gov.reject(ticket.ticket_id, reason="Exceeds daily threshold", approver="cfo")
    assert ticket.status == ApprovalStatus.REJECTED
    assert ticket.rejection_reason == "Exceeds daily threshold"
