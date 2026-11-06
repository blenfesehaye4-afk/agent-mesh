import pytest
from agent_mesh.budget import BudgetExceededError, BudgetLedger


def test_budget_cost_calculation():
    ledger = BudgetLedger()
    # gpt-4o: prompt $0.005 / 1K, completion $0.015 / 1K
    cost = ledger.calculate_cost("gpt-4o", prompt_tokens=1000, completion_tokens=1000)
    assert cost == 0.02

    # gpt-4o-mini: prompt $0.00015 / 1K, completion $0.0006 / 1K
    cost_mini = ledger.calculate_cost("gpt-4o-mini", prompt_tokens=1000, completion_tokens=1000)
    assert cost_mini == 0.00075


def test_budget_hard_cap_enforcement():
    ledger = BudgetLedger(default_budget_usd=0.01)

    # Within budget
    ledger.check_budget("tenant_a")
    ledger.record_usage("tenant_a", "gpt-4o", prompt_tokens=200, completion_tokens=200)

    # Exceeding budget
    ledger.record_usage("tenant_a", "gpt-4o", prompt_tokens=5000, completion_tokens=5000)
    with pytest.raises(BudgetExceededError, match="has exceeded budget limit"):
        ledger.check_budget("tenant_a")


def test_dynamic_cost_model_downgrading():
    ledger = BudgetLedger(default_budget_usd=10.0, default_soft_limit_usd=5.0)

    # Set quota with soft limit of $5.0
    ledger.set_quota(
        tenant_id="tenant_b",
        max_budget_usd=10.0,
        soft_limit_usd=5.0,
        downgrade_on_soft_limit=True,
        fallback_model="gpt-4o-mini",
    )

    # Under soft limit -> no downgrade
    model, downgraded = ledger.resolve_effective_model("tenant_b", "gpt-4o")
    assert model == "gpt-4o"
    assert downgraded is False

    # Simulate spend crossing soft limit ($6.0)
    quota = ledger.get_or_create_quota("tenant_b")
    quota.current_spend_usd = 6.0

    # Over soft limit -> automatic model downgrade to gpt-4o-mini
    model_downgraded, downgraded = ledger.resolve_effective_model("tenant_b", "gpt-4o")
    assert model_downgraded == "gpt-4o-mini"
    assert downgraded is True
