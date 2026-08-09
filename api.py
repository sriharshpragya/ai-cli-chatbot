# ============================================
# FastAPI wrapper for AI CLI Chatbot
# Reuses CLI modules (router, prompts, cost tracker, modes)
# Shares database with the same underlying models
# ============================================
import os
import time
import uuid
from typing import AsyncGenerator, Optional
from datetime import datetime

from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.responses import JSONResponse, StreamingResponse, Response
from fastapi.security import APIKeyHeader
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from budget import global_budget, BudgetStatus
import json

# Async OpenAI for API mode
from openai import AsyncOpenAI

# Shared modules (SAME as CLI uses)
from config import (
    OPENROUTER_API_KEY,
    DEFAULT_MODEL,
    APP_VERSION,
    APP_TITLE,
    DATABASE_ENABLED,
    REDIS_ENABLED,
)
from router import get_model_name_for_question
from modes import get_system_prompt, get_mode_list
from cost_tracker import calculate_call_cost

# Database + cache (from ai-chat-api integration)
from database.session import get_db
from database.models import User, APIKey, Conversation, Message
from database import crud
from cache.redis_client import redis_client
from cache.rate_limiter import RateLimiter
from cache.session_cache import SessionCache
from llm_client import create_chat_completion, create_streaming_completion, get_breaker_status, get_providers_status
from logging_config import configure_logging, get_logger
from middleware import RequestLoggingMiddleware
import structlog
from metrics import get_metrics_text, track_chat_request, track_llm_call

# Configure logging
configure_logging()
logger = get_logger(__name__)

# ============================================
# APP INIT
# ============================================
app = FastAPI(
    title=APP_TITLE,
    version=APP_VERSION,
    description="Production AI chatbot API - shares codebase with CLI tool",
)

# Add request logging middleware
app.add_middleware(RequestLoggingMiddleware)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

# LLM client (async for API mode)
llm_client = AsyncOpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
)

# Redis services (only if REDIS_ENABLED)
rate_limiter = RateLimiter(redis_client) if REDIS_ENABLED else None
session_cache = SessionCache(redis_client, ttl_seconds=300) if REDIS_ENABLED else None

# API key header
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


# ============================================
# LIFECYCLE EVENTS
# ============================================
@app.on_event("startup")
async def startup():
    logger.info("app_starting", app=APP_TITLE, version=APP_VERSION)
    if REDIS_ENABLED:
        try:
            await redis_client.ping()
            logger.info("redis_connected")
        except Exception as e:
            # Don't crash local/dev startup when Redis isn't up yet
            logger.error(
                "redis_ping_failed",
                error_type=type(e).__name__,
                error_message=str(e),
            )
    if DATABASE_ENABLED:
        logger.info("database_configured")
    else:
        logger.warning("database_not_configured")


@app.on_event("shutdown")
async def shutdown():
    if REDIS_ENABLED and redis_client:
        await redis_client.aclose()
    logger.info("app_shutdown")


# ============================================
# MODELS (Pydantic schemas)
# ============================================
class UserRegister(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=100)


class UserResponse(BaseModel):
    id: str
    username: str
    email: str
    tier: str
    created_at: datetime


class APIKeyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    daily_limit: int = Field(default=100, ge=1, le=100000)


class APIKeyResponse(BaseModel):
    id: str
    name: str
    key_prefix: str
    daily_limit: int
    is_active: bool
    created_at: datetime
    last_used_at: Optional[datetime] = None


class APIKeyCreated(BaseModel):
    """Returned ONCE when creating a key - includes plaintext."""
    id: str
    name: str
    key: str
    warning: str = "Save this key now. It will not be shown again."


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    mode: str = Field(default="general", description="general, ruby, python, sql, code-review")
    conversation_id: Optional[str] = None
    max_tokens: int = Field(default=500, ge=10, le=4000)

class ChatResponse(BaseModel):
    model_config = {"protected_namespaces": ()}

    response: str
    conversation_id: str
    mode: str
    model_used: str
    provider_used: str = "openrouter"
    tokens: int
    cost_usd: str
    calls_remaining_today: int


# ============================================
# AUTH DEPENDENCY
# ============================================
async def get_current_user(
    api_key: str = Depends(api_key_header),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Validate API key against database."""
    if not api_key:
        raise HTTPException(
            status_code=401,
            detail={"error": "missing_api_key", "message": "Include X-API-Key header"}
        )
    
    # Try cache first (if Redis enabled)
    if session_cache:
        cached = await session_cache.get(api_key[:16])
        if cached:
            result = await db.execute(
                select(User).where(User.id == uuid.UUID(cached["user_id"]))
            )
            user = result.scalar_one_or_none()
            if user:
                return user
    
    # Cache miss - hit database
    key_record = await crud.find_api_key(db, api_key)
    
    if not key_record:
        raise HTTPException(
            status_code=403,
            detail={"error": "invalid_api_key", "message": "API key not recognized"}
        )
    
    # Check daily quota
    calls_today = await crud.count_calls_today(db, key_record.user_id)
    if calls_today >= key_record.daily_limit:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "daily_limit_exceeded",
                "message": f"Daily limit of {key_record.daily_limit} exceeded",
                "calls_today": calls_today,
            }
        )
    
    # Cache for next time
    if session_cache:
        await session_cache.set(api_key[:16], {
            "user_id": str(key_record.user_id),
            "key_id": str(key_record.id),
            "daily_limit": key_record.daily_limit,
        })
    
    return key_record.user


async def check_rate_limit(
    request: Request,
    user: User = Depends(get_current_user),
) -> User:
    """Rate limit dependency - call this on protected endpoints."""
    if not rate_limiter:
        return user  # No rate limiting if Redis disabled
    
    allowed, info = await rate_limiter.check_limit(
        key=f"user:{user.id}",
        max_requests=5,
        window_seconds=60,
    )
    
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "rate_limit_exceeded",
                "message": f"Too many requests. Limit: {info['limit']} per {info['window_seconds']}s",
                "current_usage": info["current_usage"],
                "reset_at": info["reset_at"],
            },
            headers={
                "X-RateLimit-Limit": str(info["limit"]),
                "X-RateLimit-Remaining": str(info["remaining"]),
                "X-RateLimit-Reset": str(info["reset_at"]),
                "Retry-After": str(info["window_seconds"]),
            }
        )
    
    return user


async def _prepare_chat_request(
    db: AsyncSession,
    user: User,
    body: ChatRequest,
) -> tuple[str, Conversation, list[dict[str, str]]]:
    """Route model, resolve conversation, persist user message, build LLM messages."""
    model = get_model_name_for_question(body.message, mode=body.mode)
    system_prompt = get_system_prompt(body.mode)

    if body.conversation_id:
        conversation = await crud.get_conversation(
            db, uuid.UUID(body.conversation_id), user.id
        )
        if not conversation:
            raise HTTPException(404, {"error": "conversation_not_found"})
    else:
        conversation = await crud.create_conversation(
            db,
            user_id=user.id,
            title=body.message[:50],
            mode=body.mode,
        )

    await crud.add_message(
        db, conversation_id=conversation.id, role="user", content=body.message
    )

    history = await crud.get_conversation_history(db, conversation.id, limit=10)
    messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
    messages.extend([{"role": m.role, "content": m.content} for m in history])

    return model, conversation, messages


# ============================================
# ENDPOINTS
# ============================================

@app.get("/")
async def root():
    """Public health check."""
    return {
        "status": "healthy",
        "service": APP_TITLE,
        "version": APP_VERSION,
        "database": "enabled" if DATABASE_ENABLED else "disabled",
        "redis": "enabled" if REDIS_ENABLED else "disabled",
        "docs": "/docs",
    }


@app.get("/health")
async def deep_health_check(db: AsyncSession = Depends(get_db)):
    """Deep health check - verifies DB and Redis actually work."""
    checks = {
        "app": "healthy",
        "database": "unknown",
        "redis": "unknown",
    }
    
    try:
        result = await db.execute(text("SELECT 1"))
        result.scalar()
        checks["database"] = "healthy"
    except Exception as e:
        checks["database"] = f"error: {str(e)[:100]}"
    
    if REDIS_ENABLED:
        try:
            await redis_client.ping()
            checks["redis"] = "healthy"
        except Exception as e:
            checks["redis"] = f"error: {str(e)[:100]}"
    else:
        checks["redis"] = "disabled"
    
    all_healthy = all("healthy" in v or v == "disabled" for v in checks.values())
    
    return {
        "status": "healthy" if all_healthy else "degraded",
        "checks": checks,
        "environment": os.getenv("ENVIRONMENT", "development"),
    }


@app.get("/modes")
async def list_modes():
    """List available chatbot modes."""
    modes = get_mode_list()
    return {"modes": modes}


@app.post("/register", response_model=UserResponse, status_code=201)
async def register(
    request: UserRegister,
    db: AsyncSession = Depends(get_db),
):
    """Register a new user account."""
    if await crud.get_user_by_username(db, request.username):
        raise HTTPException(409, {"error": "username_taken"})
    if await crud.get_user_by_email(db, request.email):
        raise HTTPException(409, {"error": "email_taken"})
    
    user = await crud.create_user(
        db,
        username=request.username,
        email=request.email,
        password=request.password,
    )
    
    return UserResponse(
        id=str(user.id),
        username=user.username,
        email=user.email,
        tier=user.tier,
        created_at=user.created_at,
    )


@app.post("/me/keys", response_model=APIKeyCreated, status_code=201)
async def create_key(
    request: APIKeyCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new API key."""
    key_record, plaintext = await crud.create_api_key(
        db,
        user_id=user.id,
        name=request.name,
        daily_limit=request.daily_limit,
    )
    
    return APIKeyCreated(
        id=str(key_record.id),
        name=key_record.name,
        key=plaintext,
    )


@app.get("/me/keys", response_model=list[APIKeyResponse])
async def list_keys(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List your API keys."""
    keys = await crud.list_user_api_keys(db, user.id)
    return [
        APIKeyResponse(
            id=str(k.id),
            name=k.name,
            key_prefix=k.key_prefix,
            daily_limit=k.daily_limit,
            is_active=k.is_active,
            created_at=k.created_at,
            last_used_at=k.last_used_at,
        )
        for k in keys
    ]


@app.delete("/me/keys/{key_id}", status_code=204)
async def revoke_key(
    key_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Revoke an API key."""
    success = await crud.revoke_api_key(db, key_id, user.id)
    if not success:
        raise HTTPException(404, {"error": "key_not_found"})


@app.post("/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    user: User = Depends(check_rate_limit),
    db: AsyncSession = Depends(get_db),
):
    """Chat endpoint with structured logging and metrics."""
    
    # Bind user context
    structlog.contextvars.bind_contextvars(
        user_id=str(user.id),
        mode=body.mode,
    )
    
    logger.info(
        "chat_request_received",
        message_length=len(body.message),
        max_tokens=body.max_tokens,
    )


    # Check global budget BEFORE processing
    can_spend, budget_reason = await global_budget.can_spend(estimated_cost=0.001)
    if not can_spend:
        logger.warning("budget_blocked_request", reason=budget_reason)
        raise HTTPException(
            status_code=402,  # 402 Payment Required
            detail={
                "error": "budget_exceeded",
                "message": "Service temporarily unavailable due to budget limits",
                "retry_after": "Try again after budget period resets",
            }
        )

    # Track chat request (business metric)
    user_tier = getattr(user, 'tier', 'free')
    track_chat_request(mode=body.mode, user_tier=user_tier)
    
    model, conversation, messages = await _prepare_chat_request(db, user, body)
    
    start_time = time.time()
    
    try:
        response, provider_used, model_used = await create_chat_completion(
            model=model,
            messages=messages,
            max_tokens=body.max_tokens,
        )
        duration = time.time() - start_time
        
        # Extract usage info FIRST
        content = response.choices[0].message.content
        input_tokens = response.usage.prompt_tokens
        output_tokens = response.usage.completion_tokens

        # Calculate cost
        cost = calculate_call_cost(model_used, input_tokens, output_tokens)
        
        # Record spending
        await global_budget.record_spending(cost, provider=provider_used, model=model_used)

        # NOW track the LLM call metrics
        track_llm_call(
            provider=provider_used,
            model=model_used,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost=cost,
            duration=duration,
            success=True,
        )
        
        # Log the event
        logger.info(
            "chat_response_generated",
            provider=provider_used,
            model=model_used,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            cost_usd=cost,
        )
        
        # Persist to database
        await crud.add_message(
            db,
            conversation_id=conversation.id,
            role="assistant",
            content=content,
            model=model_used,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=f"{cost:.6f}",
        )
        
        # Calculate remaining calls
        calls_today = await crud.count_calls_today(db, user.id)
        keys = await crud.list_user_api_keys(db, user.id)
        daily_limit = max((k.daily_limit for k in keys if k.is_active), default=100)
        
        return ChatResponse(
            response=content,
            conversation_id=str(conversation.id),
            mode=body.mode,
            model_used=model_used,
            provider_used=provider_used,
            tokens=input_tokens + output_tokens,
            cost_usd=f"${cost:.6f}",
            calls_remaining_today=daily_limit - calls_today,
        )
    
    except Exception as e:
        # Track failed request (Note: individual provider failures are tracked in create_chat_completion)
        logger.error(
            "chat_request_failed",
            error_type=type(e).__name__,
            error_message=str(e),
        )
        raise

@app.post("/chat/stream")
async def chat_stream(
    http_request: Request,
    body: ChatRequest,
    user: User = Depends(check_rate_limit),
    db: AsyncSession = Depends(get_db),
):
    """Streaming chat endpoint."""
    structlog.contextvars.bind_contextvars(
        user_id=str(user.id),
        mode=body.mode,
    )
    model, conversation, messages = await _prepare_chat_request(db, user, body)

    logger.info(
        "chat_stream_request_received",
        message_length=len(body.message),
        max_tokens=body.max_tokens,
    )
    
    async def event_stream() -> AsyncGenerator[str, None]:
        try:
            stream, provider_used, model_used = await create_streaming_completion(
                model=model,
                messages=messages,
                max_tokens=body.max_tokens,
            )

            yield f"data: {json.dumps({'type': 'start', 'model': model_used, 'provider': provider_used, 'mode': body.mode})}\n\n"
            
            full_content = ""
            chunk_count = 0
            
            async for chunk in stream:
                # Check for disconnect on the HTTP request, not the body model
                if await http_request.is_disconnected():
                    logger.info(
                        "chat_stream_client_disconnected",
                        provider=provider_used,
                        model=model_used,
                        chunks_sent=chunk_count,
                    )
                    return
                
                if chunk.choices[0].delta.content:
                    chunk_count += 1
                    delta = chunk.choices[0].delta.content
                    full_content += delta
                    event = {"type": "chunk", "content": delta}
                    yield f"data: {json.dumps(event)}\n\n"
            
            # Save the complete response
            await crud.add_message(
                db,
                conversation_id=conversation.id,
                role="assistant",
                content=full_content,
                model=model_used,
            )

            logger.info(
                "chat_stream_completed",
                provider=provider_used,
                model=model_used,
                total_chunks=chunk_count,
            )
            
            done_event = {
                "type": "done",
                "conversation_id": str(conversation.id),
                "provider": provider_used,
                "model": model_used,
                "total_chunks": chunk_count,
            }
            yield f"data: {json.dumps(done_event)}\n\n"
            
        except Exception as e:
            logger.error(
                "chat_stream_failed",
                error_type=type(e).__name__,
                error_message=str(e),
            )
            error_event = {"type": "error", "message": str(e)[:200]}
            yield f"data: {json.dumps(error_event)}\n\n"
    
    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/conversations")
async def list_conversations(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List your conversations."""
    conversations = await crud.list_user_conversations(db, user.id)
    return [
        {
            "id": str(c.id),
            "title": c.title,
            "mode": c.mode,
            "created_at": c.created_at,
            "updated_at": c.updated_at,
        }
        for c in conversations
    ]


@app.get("/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get full conversation history."""
    conv = await crud.get_conversation(db, conversation_id, user.id)
    if not conv:
        raise HTTPException(404, {"error": "conversation_not_found"})
    
    return {
        "id": str(conv.id),
        "title": conv.title,
        "mode": conv.mode,
        "created_at": conv.created_at,
        "messages": [
            {
                "role": m.role,
                "content": m.content,
                "tokens": (m.input_tokens or 0) + (m.output_tokens or 0),
                "cost_usd": m.cost_usd,
                "model": m.model,
                "created_at": m.created_at,
            }
            for m in conv.messages
        ]
    }


@app.get("/me")
async def get_me(user: User = Depends(get_current_user)):
    """Get current user info."""
    return {
        "id": str(user.id),
        "username": user.username,
        "email": user.email,
        "tier": user.tier,
        "created_at": user.created_at,
    }

@app.get("/health/breaker")
async def circuit_breaker_status():
    """Check LLM circuit breaker status."""
    return get_breaker_status()

@app.get("/health/providers")
async def providers_status():
    """Check status of all LLM providers."""

    return get_providers_status()

@app.get("/metrics")
async def prometheus_metrics():
    """Expose metrics for Prometheus scraping.
    
    Not authenticated - typical practice for internal monitoring.
    Consider IP allowlist in production.
    """
    metrics_text, content_type = get_metrics_text()
    return Response(content=metrics_text, media_type=content_type)

@app.get("/health/budget")
async def budget_status():
    """Check current budget status."""
    return await global_budget.status_dict()
