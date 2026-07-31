# ============================================
# Prometheus Metrics for Production API
# ============================================
from prometheus_client import Counter, Gauge, Histogram, generate_latest, CONTENT_TYPE_LATEST

# ====== HTTP METRICS ======

http_requests_total = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status_code']
)

http_request_duration_seconds = Histogram(
    'http_request_duration_seconds',
    'HTTP request duration in seconds',
    ['method', 'endpoint'],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0)
)

http_requests_in_progress = Gauge(
    'http_requests_in_progress',
    'HTTP requests currently being processed',
    ['method', 'endpoint']
)


# ====== LLM METRICS ======

llm_calls_total = Counter(
    'llm_calls_total',
    'Total LLM API calls',
    ['provider', 'model', 'status']
)

llm_call_duration_seconds = Histogram(
    'llm_call_duration_seconds',
    'LLM call duration in seconds',
    ['provider', 'model'],
    buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0)
)

llm_tokens_total = Counter(
    'llm_tokens_total',
    'Total tokens processed',
    ['provider', 'model', 'type']
)

llm_cost_usd_total = Counter(
    'llm_cost_usd_total',
    'Total LLM cost in USD',
    ['provider', 'model']
)


# ====== PROVIDER HEALTH ======

provider_health = Gauge(
    'provider_health',
    'Provider health (1=healthy, 0.5=degraded, 0=unhealthy)',
    ['provider']
)

provider_circuit_breaker_state = Gauge(
    'provider_circuit_breaker_state',
    'Circuit breaker state (0=closed, 1=half_open, 2=open)',
    ['provider']
)

fallback_used_total = Counter(
    'fallback_used_total',
    'Fallback provider used',
    ['from_provider', 'to_provider', 'reason']
)


# ====== BUSINESS METRICS ======

chat_requests_total = Counter(
    'chat_requests_total',
    'Total chat requests',
    ['mode', 'user_tier']
)

rate_limit_exceeded_total = Counter(
    'rate_limit_exceeded_total',
    'Rate limit rejections',
    ['user_tier']
)

active_users = Gauge(
    'active_users',
    'Users active in last 5 minutes'
)


# ====== HELPER FUNCTIONS ======

def track_llm_call(provider: str, model: str, input_tokens: int, output_tokens: int, cost: float, duration: float, success: bool):
    """Record all metrics for an LLM call."""
    status = 'success' if success else 'failure'
    
    llm_calls_total.labels(provider=provider, model=model, status=status).inc()
    llm_call_duration_seconds.labels(provider=provider, model=model).observe(duration)
    llm_tokens_total.labels(provider=provider, model=model, type='input').inc(input_tokens)
    llm_tokens_total.labels(provider=provider, model=model, type='output').inc(output_tokens)
    llm_cost_usd_total.labels(provider=provider, model=model).inc(cost)


def track_chat_request(mode: str, user_tier: str = 'free'):
    """Record a chat request."""
    chat_requests_total.labels(mode=mode, user_tier=user_tier).inc()


def track_rate_limit_exceeded(user_tier: str = 'free'):
    """Record rate limit rejection."""
    rate_limit_exceeded_total.labels(user_tier=user_tier).inc()


def track_fallback(from_provider: str, to_provider: str, reason: str):
    """Record fallback usage."""
    fallback_used_total.labels(
        from_provider=from_provider,
        to_provider=to_provider,
        reason=reason,
    ).inc()


def update_provider_health(provider: str, health: str):
    """Update provider health gauge."""
    values = {'healthy': 1.0, 'degraded': 0.5, 'unhealthy': 0.0}
    provider_health.labels(provider=provider).set(values.get(health, 0))


def update_circuit_breaker_state(provider: str, state: str):
    """Update circuit breaker state gauge."""
    values = {'closed': 0, 'half_open': 1, 'open': 2}
    provider_circuit_breaker_state.labels(provider=provider).set(values.get(state, 0))


def get_metrics_text() -> tuple[str, str]:
    """Get metrics in Prometheus text format."""
    return generate_latest().decode('utf-8'), CONTENT_TYPE_LATEST