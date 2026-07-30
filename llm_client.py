# ============================================
# LLM Client with Retry + Async Circuit Breaker
# Production-grade resilience for LLM calls
# ============================================
import logging
from datetime import timedelta
from openai import (
    AsyncOpenAI,
    RateLimitError,
    APITimeoutError,
    APIConnectionError,
    InternalServerError,
)
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential_jitter,
    retry_if_exception_type,
    before_sleep_log,
)
from aiobreaker import CircuitBreaker, CircuitBreakerListener, CircuitBreakerError
from config import OPENROUTER_API_KEY

logger = logging.getLogger(__name__)

_client = AsyncOpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
    timeout=60.0,
    max_retries=0,
)

RETRIABLE_EXCEPTIONS = (
    RateLimitError,
    APITimeoutError,
    APIConnectionError,
    InternalServerError,
)

class LLMBreakerListener(CircuitBreakerListener):
    def state_change(self, cb, old_state, new_state):
        logger.warning(f"Circuit breaker: {old_state} → {new_state}")

llm_breaker = CircuitBreaker(
    fail_max=5,
    timeout_duration=timedelta(seconds=30),
    listeners=[LLMBreakerListener()],
    name="openrouter_breaker",
)

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential_jitter(initial=1, max=10, jitter=2),
    retry=retry_if_exception_type(RETRIABLE_EXCEPTIONS),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
async def _call_with_retry(**kwargs):
    return await _client.chat.completions.create(**kwargs)


@llm_breaker
async def create_chat_completion(**kwargs):
    """Circuit breaker wraps retry logic."""
    return await _call_with_retry(**kwargs)


@llm_breaker
async def create_streaming_completion(**kwargs):
    """Streaming with retry (but not for streaming failures mid-stream)."""
    kwargs["stream"] = True
    return await _client.chat.completions.create(**kwargs)


def get_breaker_status() -> dict:
    state = llm_breaker.current_state
    return {
        # Enum is not JSON-serializable — return the name string
        "state": state.name if hasattr(state, "name") else str(state),
        "failure_count": llm_breaker.fail_counter,
        "failure_threshold": llm_breaker.fail_max,
    }
