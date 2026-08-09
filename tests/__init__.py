# ============================================
# Unit Tests for Budget Management
# ============================================
import pytest
from unittest.mock import AsyncMock, patch
from budget import GlobalBudget, BudgetStatus


@pytest.fixture
def mock_redis():
    """Mock Redis client that returns dict-like storage."""
    storage = {}
    
    async def get(key):
        return storage.get(key)
    
    async def incrbyfloat(key, amount):
        current = float(storage.get(key, 0))
        new_value = current + amount
        storage[key] = str(new_value)
        return new_value
    
    async def expire(key, seconds):
        pass  # No-op for tests
    
    mock = AsyncMock()
    mock.get = get
    mock.incrbyfloat = incrbyfloat
    mock.expire = expire
    return mock


@pytest.fixture
def budget(mock_redis):
    """Fresh budget with test configuration."""
    with patch('budget.get_redis', return_value=mock_redis):
        budget = GlobalBudget()
        budget.daily_budget = 1.0    # $1 for testing
        budget.monthly_budget = 10.0  # $10 for testing
        yield budget


@pytest.mark.asyncio
async def test_healthy_status_when_no_spending(budget):
    """Budget starts as HEALTHY with zero spending."""
    status = await budget.check_status()
    assert status == BudgetStatus.HEALTHY


@pytest.mark.asyncio
async def test_warning_status_at_80_percent(budget):
    """Budget becomes WARNING at 80% of daily limit."""
    # Spend 80% of $1 = $0.80
    await budget.record_spending(0.80)
    
    status = await budget.check_status()
    assert status == BudgetStatus.WARNING


@pytest.mark.asyncio
async def test_critical_status_at_95_percent(budget):
    """Budget becomes CRITICAL at 95%."""
    await budget.record_spending(0.95)
    
    status = await budget.check_status()
    assert status == BudgetStatus.CRITICAL


@pytest.mark.asyncio
async def test_exceeded_at_100_percent(budget):
    """Budget becomes EXCEEDED at 100%."""
    await budget.record_spending(1.00)
    
    status = await budget.check_status()
    assert status == BudgetStatus.EXCEEDED


@pytest.mark.asyncio
async def test_can_spend_when_healthy(budget):
    """Can spend when under budget."""
    can_spend, reason = await budget.can_spend(0.50)
    assert can_spend is True
    assert reason == "OK"


@pytest.mark.asyncio
async def test_cannot_spend_over_daily_budget(budget):
    """Cannot spend if it would exceed daily budget."""
    await budget.record_spending(0.90)
    
    can_spend, reason = await budget.can_spend(0.20)  # Would total $1.10
    assert can_spend is False
    assert "Daily budget" in reason


@pytest.mark.asyncio
async def test_status_dict_structure(budget):
    """Status dict has expected structure."""
    await budget.record_spending(0.30)
    
    status = await budget.status_dict()
    
    assert "status" in status
    assert "daily" in status
    assert "monthly" in status
    assert status["daily"]["spent_usd"] == 0.3
    assert status["daily"]["budget_usd"] == 1.0
    assert status["daily"]["percentage"] == 30.0


@pytest.mark.asyncio
async def test_spending_accumulates(budget):
    """Multiple spending events accumulate."""
    await budget.record_spending(0.10)
    await budget.record_spending(0.20)
    await budget.record_spending(0.05)
    
    daily, _ = await budget.get_current_spending()
    assert daily == pytest.approx(0.35)


@pytest.mark.asyncio
async def test_monthly_tracks_separately(budget):
    """Monthly and daily spending track independently."""
    await budget.record_spending(0.50)
    
    daily, monthly = await budget.get_current_spending()
    assert daily == 0.50
    assert monthly == 0.50
    # Both same since only one day of spending