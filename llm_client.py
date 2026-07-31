# ============================================
# LLM Client with Full Resilience
# Retry + Circuit Breaker + Multi-Provider Fallback
# ============================================
import logging
import time
import os
from enum import Enum
from openai import (
    AsyncOpenAI,
    RateLimitError,
    APITimeoutError,
    APIConnectionError,
    InternalServerError,
    AuthenticationError,
)
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential_jitter,
    retry_if_exception_type,
    before_sleep_log,
)
import aiobreaker
from datetime import timedelta
from config import OPENROUTER_API_KEY

logger = logging.getLogger(__name__)


RETRIABLE_EXCEPTIONS = (
    RateLimitError,
    APITimeoutError,
    APIConnectionError,
    InternalServerError,
)


# ====== PROVIDER STATUS ======

class ProviderStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


# ====== PROVIDER CLASS (with own circuit breaker) ======

class LLMProvider:
    """
    LLM provider with:
    - Health tracking (for fallback decisions)
    - Circuit breaker (protects THIS provider from cascading failures)
    - Own client instance
    """
    
    def __init__(
        self,
        name: str,
        client: AsyncOpenAI,
        default_model: str,
        priority: int,
        failure_threshold: int = 3,
        recovery_timeout: float = 60.0,
    ):
        self.name = name
        self.client = client
        self.default_model = default_model
        self.priority = priority
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        
        # Health tracking (for fallback)
        self.status = ProviderStatus.HEALTHY
        self.failure_count = 0
        self.last_failure_time = None
        
        # Circuit breaker (protects this specific provider)
        self.breaker = aiobreaker.CircuitBreaker(
            fail_max=failure_threshold,
            timeout_duration=timedelta(seconds=recovery_timeout),
            name=f"{name}_breaker",
        )
    
    def is_available(self) -> bool:
        """Check if this provider should be tried."""
        if self.status == ProviderStatus.UNHEALTHY:
            if self.last_failure_time and time.time() - self.last_failure_time >= self.recovery_timeout:
                logger.info(f"{self.name}: recovery timeout elapsed")
                self.status = ProviderStatus.DEGRADED
                return True
            return False
        return True
    
    def record_success(self):
        was_degraded = self.status != ProviderStatus.HEALTHY
        self.status = ProviderStatus.HEALTHY
        self.failure_count = 0
        if was_degraded:
            logger.info(f"{self.name}: RECOVERED, marked HEALTHY")
    
    def record_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.failure_count >= self.failure_threshold:
            self.status = ProviderStatus.UNHEALTHY
            logger.warning(
                f"{self.name}: UNHEALTHY after {self.failure_count} failures. "
                f"Recovery in {self.recovery_timeout}s"
            )
        else:
            self.status = ProviderStatus.DEGRADED
    
    def status_dict(self) -> dict:
        """Combined status: health + circuit breaker."""
        breaker_state = self.breaker.current_state
        return {
            "name": self.name,
            "status": self.status.value,
            "priority": self.priority,
            "failure_count": self.failure_count,
            "default_model": self.default_model,
            "circuit_breaker": {
                "state": breaker_state.name if hasattr(breaker_state, "name") else str(breaker_state),
                "failure_count": self.breaker.fail_counter,
                "failure_threshold": self.breaker.fail_max,
            },
        }


# ====== INITIALIZE PROVIDERS ======

def _create_providers() -> list[LLMProvider]:
    providers = []
    
    if OPENROUTER_API_KEY:
        providers.append(LLMProvider(
            name="openrouter",
            client=AsyncOpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=OPENROUTER_API_KEY,
                timeout=60.0,
                max_retries=0,
            ),
            default_model="openai/gpt-4o-mini",
            priority=1,
        ))
    
    groq_key = os.getenv("GROQ_API_KEY")
    if groq_key:
        providers.append(LLMProvider(
            name="groq",
            client=AsyncOpenAI(
                base_url="https://api.groq.com/openai/v1",
                api_key=groq_key,
                timeout=60.0,
                max_retries=0,
            ),
            default_model="llama-3.1-8b-instant",
            priority=2,
        ))
    
    if not providers:
        raise ValueError("No LLM providers configured")
    
    providers.sort(key=lambda p: p.priority)
    logger.info(f"Initialized providers: {[p.name for p in providers]}")
    return providers


PROVIDERS = _create_providers()


# ====== CALL WITH RETRY (per provider) ======

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential_jitter(initial=1, max=10, jitter=2),
    retry=retry_if_exception_type(RETRIABLE_EXCEPTIONS),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
async def _call_provider_with_retry(provider: LLMProvider, **kwargs):
    """Retry logic for a single provider call. Returns (response, model_used)."""
    # OpenRouter-style IDs (openai/...) are invalid on Groq — swap to provider default
    model = kwargs.get("model", "")
    if model.startswith("openai/") and provider.name != "openrouter":
        model = provider.default_model
        kwargs["model"] = model
    elif provider.name != "openrouter" and "/" in model and not model.startswith(provider.name):
        # Other OpenRouter vendor IDs also won't work on Groq
        model = provider.default_model
        kwargs["model"] = model

    response = await provider.client.chat.completions.create(**kwargs)
    return response, model


# ====== MAIN CHAT WITH FALLBACK ======

async def create_chat_completion(**kwargs):
    """
    Full resilience stack:
    1. Circuit breaker per provider (Day 20)
    2. Retry per provider (Day 19)
    3. Fallback to next provider (Day 21)

    Returns: (response, provider_name, model_used)
    """
    last_error = None
    attempted = []
    
    for provider in PROVIDERS:
        # Skip unhealthy providers
        if not provider.is_available():
            logger.debug(f"Skipping {provider.name} (unhealthy)")
            continue
        
        attempted.append(provider.name)
        
        try:
            # Wrap the call with circuit breaker
            async def call():
                return await _call_provider_with_retry(provider, **kwargs)
            
            # Circuit breaker wraps retry
            response, model_used = await provider.breaker.call_async(call)
            
            provider.record_success()
            logger.info(f"✅ Success from {provider.name} (model={model_used})")
            return response, provider.name, model_used
        
        except aiobreaker.CircuitBreakerError:
            logger.warning(f"{provider.name}: circuit OPEN, skipping")
            provider.record_failure()
            continue
        
        except AuthenticationError as e:
            logger.error(f"{provider.name}: AuthenticationError - check credentials")
            provider.record_failure()
            last_error = e
            continue
        
        except Exception as e:
            logger.warning(f"{provider.name}: failed with {type(e).__name__}")
            provider.record_failure()
            last_error = e
            continue
    
    if not attempted:
        raise Exception("All providers currently unavailable")
    
    raise Exception(f"All providers failed. Attempted: {attempted}. Last: {type(last_error).__name__}: {last_error}")


# ====== STREAMING ======

async def create_streaming_completion(**kwargs):
    """Streaming with fallback. Returns: (stream, provider_name, model_used)."""
    for provider in PROVIDERS:
        if not provider.is_available():
            continue
        
        try:
            model = kwargs.get("model", "")
            if model.startswith("openai/") and provider.name != "openrouter":
                model = provider.default_model
            elif provider.name != "openrouter" and "/" in model:
                model = provider.default_model

            call_kwargs = {**kwargs, "model": model, "stream": True}
            
            async def call():
                return await provider.client.chat.completions.create(**call_kwargs)
            
            stream = await provider.breaker.call_async(call)
            provider.record_success()
            return stream, provider.name, model
        
        except Exception as e:
            logger.warning(f"{provider.name} streaming failed: {type(e).__name__}")
            provider.record_failure()
            continue
    
    raise Exception("All providers failed for streaming")


# ====== HEALTH CHECK FUNCTIONS ======

def get_providers_status() -> dict:
    """Get status of all providers (health + circuit breakers)."""
    return {
        "total_providers": len(PROVIDERS),
        "healthy_count": sum(1 for p in PROVIDERS if p.is_available()),
        "providers": [p.status_dict() for p in PROVIDERS],
    }


def get_breaker_status() -> dict:
    """
    Backwards compat: return primary provider's circuit breaker status.
    Used by /health/breaker endpoint from Day 20.
    """
    if not PROVIDERS:
        return {"error": "no providers configured"}
    
    primary = PROVIDERS[0]  # Highest priority
    breaker_state = primary.breaker.current_state
    return {
        "provider": primary.name,
        "state": breaker_state.name if hasattr(breaker_state, "name") else str(breaker_state),
        "failure_count": primary.breaker.fail_counter,
        "failure_threshold": primary.breaker.fail_max,
        "note": "Use /health/providers for full multi-provider status",
    }