# ============================================
# Central configuration
# Supports both CLI mode (minimal) and API mode (full)
# ============================================
import os
from dotenv import load_dotenv

load_dotenv()


def _get_openrouter_key() -> str:
    """OpenRouter key is REQUIRED for both modes."""
    key = os.getenv("OPENROUTER_API_KEY", "")
    if not key:
        raise ValueError(
            "OPENROUTER_API_KEY environment variable is required. "
            "Get one at https://openrouter.ai"
        )
    return key


def _get_database_url() -> str:
    """
    Database URL is OPTIONAL for CLI, REQUIRED for API.
    Returns empty string if not set (CLI can still work).
    """
    url = os.getenv("DATABASE_URL", "")
    
    if url:
        # Convert to async-compatible format
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        elif url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    
    return url


def _get_redis_url() -> str:
    """Redis URL is OPTIONAL for CLI, REQUIRED for API."""
    return os.getenv("REDIS_URL", "")


# ====== Required config ======
OPENROUTER_API_KEY = _get_openrouter_key()

# ====== Optional config (empty for CLI-only mode) ======
DATABASE_URL = _get_database_url()
REDIS_URL = _get_redis_url()

# ====== Feature flags ======
DATABASE_ENABLED = bool(DATABASE_URL)
REDIS_ENABLED = bool(REDIS_URL)

# ====== App settings ======
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
DEBUG = os.getenv("DEBUG", "false").lower() == "true"

# ====== LLM defaults ======
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "openai/gpt-4o-mini")

# ====== App metadata ======
APP_VERSION = "3.0.0"
APP_TITLE = "AI CLI Chatbot"

# Print startup config
if ENVIRONMENT != "production":
    print(f"[CONFIG] Environment: {ENVIRONMENT}")
    print(f"[CONFIG] Database: {'ENABLED' if DATABASE_ENABLED else 'DISABLED (CLI mode)'}")
    print(f"[CONFIG] Redis: {'ENABLED' if REDIS_ENABLED else 'DISABLED (CLI mode)'}")
    print(f"[CONFIG] Model: {DEFAULT_MODEL}")
