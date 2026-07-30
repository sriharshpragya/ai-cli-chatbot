# ============================================
# LLM Client with Retry Logic
# Production-grade wrapper around OpenAI SDK
# ============================================
import logging
from openai import (
    AsyncOpenAI, 
    RateLimitError, 
    APITimeoutError, 
    APIConnectionError,
    InternalServerError,  # 5xx errors
)
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential_jitter,
    retry_if_exception_type,
    before_sleep_log,
)
from config import OPENROUTER_API_KEY

logger = logging.getLogger(__name__)

# Base client
_client = AsyncOpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
    timeout=60.0,  # 60 second timeout per request
    max_retries=0,  # Disable OpenAI's built-in retries (we handle it)
)


# Retriable exceptions
RETRIABLE_EXCEPTIONS = (
    RateLimitError,        # 429 - slow down
    APITimeoutError,       # request timeout
    APIConnectionError,    # network issue
    InternalServerError,   # 5xx from provider
)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential_jitter(initial=1, max=10, jitter=2),
    retry=retry_if_exception_type(RETRIABLE_EXCEPTIONS),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
async def create_chat_completion(**kwargs):
    """
    Async wrapper for chat completions with retries.
    
    Retries on transient failures (rate limits, timeouts, 5xx).
    Fails fast on user errors (400, 401, 403).
    """
    return await _client.chat.completions.create(**kwargs)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential_jitter(initial=1, max=10, jitter=2),
    retry=retry_if_exception_type(RETRIABLE_EXCEPTIONS),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
async def create_streaming_completion(**kwargs):
    """Streaming version - retries the initial connection."""
    kwargs["stream"] = True
    return await _client.chat.completions.create(**kwargs)