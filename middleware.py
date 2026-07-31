# ============================================
# FastAPI Middleware for Request Logging
# ============================================
import uuid
import time
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from logging_config import get_logger
import structlog
from metrics import (
    http_requests_total,
    http_request_duration_seconds,
    http_requests_in_progress,
)

logger = get_logger(__name__)

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log every HTTP request with unique request ID."""
    
    async def dispatch(self, request: Request, call_next):
        # Skip metrics endpoint (avoid self-monitoring)
        if request.url.path == "/metrics":
            return await call_next(request)
        
        # Skip health checks (too noisy for metrics too)
        skip_paths = ["/health", "/health/breaker", "/health/providers"]
        if request.url.path in skip_paths:
            return await call_next(request)
        
        method = request.method
        endpoint = request.url.path

        # Extract or generate reques{t} ID
        request_id = request.headers.get("X-Request-ID") or f"req_{uuid.uuid4().hex[:12]}"
        
        # Skip logging for health checks (too noisy)
        skip_paths = ["/health", "/health/breaker", "/health/providers", "/"]
        if request.url.path in skip_paths:
            return await call_next(request)
        
        # Bind context to all logs in this request
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
        )
        
        # Extract user info from headers (if API key present)
        api_key = request.headers.get("X-API-Key", "")
        if api_key:
            # Only log first/last chars for security
            structlog.contextvars.bind_contextvars(
                api_key_prefix=api_key[:10] if len(api_key) > 10 else "invalid",
            )
        
        # Log request start
        logger.info(
            "http_request_started",
            client_host=request.client.host if request.client else "unknown",
            user_agent=request.headers.get("user-agent", "unknown")[:100],
        )
        
        # Track in-progress
        http_requests_in_progress.labels(method=method, endpoint=endpoint).inc()
        # Process request with timing and track metrics
        start_time = time.time()
        status_code = "500"  # Default in case of exception
        
        try:
            response = await call_next(request)
            elapsed_ms = round((time.time() - start_time) * 1000, 2)
            
            # Log success
            logger.info(
                "http_request_completed",
                status_code=response.status_code,
                latency_ms=elapsed_ms,
            )
            
            # Add request ID to response
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Response-Time"] = f"{elapsed_ms:.2f}ms"
            return response
        
        except Exception as e:
            elapsed_ms = round((time.time() - start_time) * 1000, 2)
            
            logger.error(
                "http_request_failed",
                error_type=type(e).__name__,
                error_message=str(e),
                latency_ms=elapsed_ms,
                exc_info=True,
            )
            raise
        finally:
            # Record metrics regardless of success/failure
            duration = time.time() - start_time
            
            http_request_duration_seconds.labels(
                method=method, endpoint=endpoint
            ).observe(duration)
            
            http_requests_total.labels(
                method=method, endpoint=endpoint, status_code=status_code
            ).inc()
            
            http_requests_in_progress.labels(method=method, endpoint=endpoint).dec()
            
            structlog.contextvars.clear_contextvars()