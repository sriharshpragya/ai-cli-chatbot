# ============================================
# Structured Logging Configuration
# ============================================
import os
import sys
import logging
import structlog
from typing import Any

# Environment
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()


def configure_logging():
    """Configure structured logging for the application."""
    
    # Determine processors based on environment
    if ENVIRONMENT == "development":
        # Pretty console output for development
        processors = [
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="%H:%M:%S"),
            structlog.dev.ConsoleRenderer(colors=True),
        ]
    else:
        # JSON output for production (parseable by log aggregators)
        processors = [
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.dict_tracebacks,  # Include tracebacks in JSON
            structlog.processors.JSONRenderer(),
        ]
    
    # Configure structlog
    structlog.configure(
        processors=processors,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    
    # Configure stdlib logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=LOG_LEVEL,
    )
    
    # Silence noisy libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def get_logger(name: str = None) -> Any:
    """Get a structured logger instance."""
    return structlog.get_logger(name)


# Configure on import
configure_logging()