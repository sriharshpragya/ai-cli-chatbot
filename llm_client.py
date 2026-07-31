# ============================================
# LLM Client with Full Resilience
# Retry + Circuit Breaker + Multi-Provider Fallback
# ============================================
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
)
import aiobreaker
from datetime import timedelta
from config import OPENROUTER_API_KEY
from logging_config import get_logger
from metrics import (
    update_provider_health,
    update_circuit_breaker_state,
    track_fallback,
    track_llm_call,
)

logger = get_logger(__name__)

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
                logger.info(
                    "provider_recovery_timeout_elapsed",
                    provider=self.name,
                )
                self.status = ProviderStatus.DEGRADED
                return True
            return False
        return True
    
    def record_success(self):
        was_degraded = self.status != ProviderStatus.HEALTHY
        self.status = ProviderStatus.HEALTHY
        self.failure_count = 0
        if was_degraded:
            logger.info("provider_recovered", provider=self.name)
        update_provider_health(self.name, ProviderStatus.HEALTHY)
    
    def record_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.failure_count >= self.failure_threshold:
            self.status = ProviderStatus.UNHEALTHY
            logger.warning(
                "provider_unhealthy",
                provider=self.name,
                failure_count=self.failure_count,
                recovery_timeout_s=self.recovery_timeout,
            )
        else:
            self.status = ProviderStatus.DEGRADED
            logger.warning(
                "provider_degraded",
                provider=self.name,
                failure_count=self.failure_count,
                failure_threshold=self.failure_threshold,
            )
        
        if self.status == ProviderStatus.UNHEALTHY:
            update_provider_health(self.name, ProviderStatus.UNHEALTHY)
        else:
            update_provider_health(self.name, ProviderStatus.DEGRADED)
    
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
    logger.info(
        "providers_initialized",
        providers=[p.name for p in providers],
        count=len(providers),
    )
    return providers


PROVIDERS = _create_providers()


# ====== CALL WITH RETRY (per provider) ======

def _before_sleep_log(retry_state):
    exc = retry_state.outcome.exception() if retry_state.outcome else None
    logger.warning(
        "provider_retry",
        attempt=retry_state.attempt_number,
        error_type=type(exc).__name__ if exc else None,
        error_message=str(exc) if exc else None,
        wait_s=getattr(retry_state.next_action, "sleep", None),
    )


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential_jitter(initial=1, max=10, jitter=2),
    retry=retry_if_exception_type(RETRIABLE_EXCEPTIONS),
    before_sleep=_before_sleep_log,
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
    Full resilience stack with metrics:
    1. Circuit breaker per provider (Day 20)
    2. Retry per provider (Day 19)
    3. Fallback to next provider (Day 21)
    4. Metrics tracking (Day 23)
    
    Returns: (response, provider_name, model_used)
    """
    last_error = None
    attempted = []
    previous_provider = None
    previous_provider_reason = None
    requested_model = kwargs.get('model', 'unknown')
    
    for provider in PROVIDERS:
        # Skip unhealthy providers
        if not provider.is_available():
            logger.debug("provider_skipped", provider=provider.name, reason="unhealthy")
            continue
        
        attempted.append(provider.name)
        provider_start_time = time.time()
        
        try:
            async def call():
                logger.info("provider_attempt", provider=provider.name)
                return await _call_provider_with_retry(provider, **kwargs)
            
            # Circuit breaker wraps retry - returns (response, model_used)
            response, model_used = await provider.breaker.call_async(call)
            provider_duration = time.time() - provider_start_time
            
            # Track fallback if we came from a failed provider
            if previous_provider:
                track_fallback(
                    from_provider=previous_provider,
                    to_provider=provider.name,
                    reason=previous_provider_reason or "unknown",
                )
            
            # Log success
            usage = getattr(response, "usage", None)
            logger.info(
                "provider_success",
                provider=provider.name,
                model=model_used,
                tokens=usage.total_tokens if usage else None,
                duration_ms=round(provider_duration * 1000, 2),
            )
            
            provider.record_success()
            return response, provider.name, model_used
        
        except aiobreaker.CircuitBreakerError:
            provider_duration = time.time() - provider_start_time
            logger.warning("provider_circuit_open", provider=provider.name)
            provider.record_failure()
            
            # Track failed attempt
            track_llm_call(
                provider=provider.name,
                model=requested_model,
                input_tokens=0,
                output_tokens=0,
                cost=0,
                duration=provider_duration,
                success=False,
            )
            
            previous_provider = provider.name
            previous_provider_reason = "circuit_open"
            continue
        
        except AuthenticationError as e:
            provider_duration = time.time() - provider_start_time
            logger.error("provider_auth_error", provider=provider.name)
            provider.record_failure()
            
            track_llm_call(
                provider=provider.name,
                model=requested_model,
                input_tokens=0,
                output_tokens=0,
                cost=0,
                duration=provider_duration,
                success=False,
            )
            
            previous_provider = provider.name
            previous_provider_reason = "auth_error"
            last_error = e
            continue
        
        except Exception as e:
            provider_duration = time.time() - provider_start_time
            logger.warning(
                "provider_failed",
                provider=provider.name,
                error_type=type(e).__name__,
                error_message=str(e),
                duration_ms=round(provider_duration * 1000, 2),
            )
            provider.record_failure()
            
            track_llm_call(
                provider=provider.name,
                model=requested_model,
                input_tokens=0,
                output_tokens=0,
                cost=0,
                duration=provider_duration,
                success=False,
            )
            
            previous_provider = provider.name
            previous_provider_reason = type(e).__name__
            last_error = e
            continue
    
    # No providers were available
    if not attempted:
        logger.error("all_providers_unavailable")
        raise Exception("All providers currently unavailable")
    
    # All attempted providers failed
    logger.error(
        "all_providers_failed",
        attempted=attempted,
        last_error_type=type(last_error).__name__,
        last_error=str(last_error) if last_error else None,
    )
    raise Exception(
        f"All providers failed. Attempted: {attempted}. "
        f"Last: {type(last_error).__name__}: {last_error}"
    )

# ====== STREAMING ======

async def create_streaming_completion(**kwargs):
    """Streaming with fallback. Returns: (stream, provider_name, model_used)."""
    for provider in PROVIDERS:
        if not provider.is_available():
            logger.debug("provider_skipped", provider=provider.name, reason="unhealthy")
            continue
        
        try:
            model = kwargs.get("model", "")
            if model.startswith("openai/") and provider.name != "openrouter":
                model = provider.default_model
            elif provider.name != "openrouter" and "/" in model:
                model = provider.default_model

            call_kwargs = {**kwargs, "model": model, "stream": True}
            
            async def call():
                logger.info("provider_stream_attempt", provider=provider.name, model=model)
                return await provider.client.chat.completions.create(**call_kwargs)
            
            stream = await provider.breaker.call_async(call)
            provider.record_success()
            logger.info("provider_stream_success", provider=provider.name, model=model)
            return stream, provider.name, model
        
        except aiobreaker.CircuitBreakerError:
            logger.warning("provider_circuit_open", provider=provider.name)
            provider.record_failure()
            continue
        
        except Exception as e:
            logger.warning(
                "provider_stream_failed",
                provider=provider.name,
                error_type=type(e).__name__,
                error_message=str(e),
            )
            provider.record_failure()
            continue
    
    logger.error("all_providers_failed", mode="streaming")
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
