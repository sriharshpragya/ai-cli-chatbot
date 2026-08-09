# ============================================
# Cost Budget Management
# ============================================
import os
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from cache.redis_client import get_redis
import structlog

logger = structlog.get_logger()


class BudgetStatus(str, Enum):
    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    EXCEEDED = "exceeded"


class GlobalBudget:
    """
    System-wide budget across all users.
    Uses Redis for persistence across app restarts.
    """
    
    def __init__(self):
        self.daily_budget = float(os.getenv("DAILY_BUDGET_USD", "5.00"))
        self.monthly_budget = float(os.getenv("MONTHLY_BUDGET_USD", "100.00"))
        self.warning_threshold = float(os.getenv("BUDGET_WARNING_THRESHOLD", "0.80"))
        self.critical_threshold = float(os.getenv("BUDGET_CRITICAL_THRESHOLD", "0.95"))
    
    def _get_keys(self):
        """Get Redis keys with date suffixes for auto-expiry."""
        now = datetime.now(timezone.utc)
        daily_key = f"budget:daily:{now.strftime('%Y-%m-%d')}"
        monthly_key = f"budget:monthly:{now.strftime('%Y-%m')}"
        return daily_key, monthly_key
    
    async def get_current_spending(self) -> tuple[float, float]:
        """Get current daily and monthly spending from Redis."""
        try:
            redis = await get_redis()
            daily_key, monthly_key = self._get_keys()
            
            daily = await redis.get(daily_key)
            monthly = await redis.get(monthly_key)
            
            return (
                float(daily) if daily else 0.0,
                float(monthly) if monthly else 0.0,
            )
        except Exception as e:
            logger.warning("budget_redis_error", error=str(e))
            # Fail open - don't block on Redis errors
            return 0.0, 0.0
    
    async def record_spending(self, amount_usd: float, provider: str = "", model: str = ""):
        """Record spending in Redis with automatic expiration."""
        try:
            redis = await get_redis()
            daily_key, monthly_key = self._get_keys()
            
            # Use INCRBYFLOAT for atomic increment
            new_daily = await redis.incrbyfloat(daily_key, amount_usd)
            new_monthly = await redis.incrbyfloat(monthly_key, amount_usd)
            
            # Set expiration (keys auto-delete after period ends)
            # Daily keys expire after 2 days (safety buffer)
            # Monthly keys expire after 32 days
            await redis.expire(daily_key, 2 * 24 * 3600)
            await redis.expire(monthly_key, 32 * 24 * 3600)
            
            status = await self.check_status()
            
            logger.info(
                "cost_recorded",
                amount_usd=amount_usd,
                provider=provider,
                model=model,
                daily_total=new_daily,
                monthly_total=new_monthly,
                status=status.value,
            )
            
            return new_daily, new_monthly
            
        except Exception as e:
            logger.error("budget_record_failed", error=str(e))
            return 0.0, 0.0
    
    async def check_status(self) -> BudgetStatus:
        """Check current budget health."""
        daily, monthly = await self.get_current_spending()
        
        daily_pct = daily / self.daily_budget if self.daily_budget > 0 else 0
        monthly_pct = monthly / self.monthly_budget if self.monthly_budget > 0 else 0
        worst_pct = max(daily_pct, monthly_pct)
        
        if worst_pct >= 1.0:
            return BudgetStatus.EXCEEDED
        elif worst_pct >= self.critical_threshold:
            return BudgetStatus.CRITICAL
        elif worst_pct >= self.warning_threshold:
            return BudgetStatus.WARNING
        else:
            return BudgetStatus.HEALTHY
    
    async def can_spend(self, estimated_cost: float = 0.001) -> tuple[bool, str]:
        """
        Check if system budget allows this call.
        Returns: (can_afford, reason)
        """
        daily, monthly = await self.get_current_spending()
        
        projected_daily = daily + estimated_cost
        projected_monthly = monthly + estimated_cost
        
        if projected_daily > self.daily_budget:
            return False, f"Daily budget ${self.daily_budget:.2f} exceeded (${daily:.4f} spent)"
        
        if projected_monthly > self.monthly_budget:
            return False, f"Monthly budget ${self.monthly_budget:.2f} exceeded (${monthly:.4f} spent)"
        
        return True, "OK"
    
    async def status_dict(self) -> dict:
        """Get full budget status."""
        daily, monthly = await self.get_current_spending()
        status = await self.check_status()
        
        return {
            "status": status.value,
            "daily": {
                "spent_usd": round(daily, 6),
                "budget_usd": self.daily_budget,
                "percentage": round(daily / self.daily_budget * 100, 2) if self.daily_budget > 0 else 0,
                "remaining_usd": round(max(0, self.daily_budget - daily), 6),
            },
            "monthly": {
                "spent_usd": round(monthly, 6),
                "budget_usd": self.monthly_budget,
                "percentage": round(monthly / self.monthly_budget * 100, 2) if self.monthly_budget > 0 else 0,
                "remaining_usd": round(max(0, self.monthly_budget - monthly), 6),
            },
            "thresholds": {
                "warning": self.warning_threshold,
                "critical": self.critical_threshold,
            },
        }


# Global instance
global_budget = GlobalBudget()