# ============================================
# CRUD operations — reusable database functions
# All functions take a session and use async SQLAlchemy
# ============================================
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func
from sqlalchemy.orm import selectinload
from passlib.context import CryptContext
from typing import Optional
import secrets

from database.models import User, APIKey, Conversation, Message

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ====== USER CRUD ======

async def get_user_by_username(db: AsyncSession, username: str) -> Optional[User]:
    result = await db.execute(select(User).where(User.username == username))
    return result.scalar_one_or_none()


async def get_user_by_email(db: AsyncSession, email: str) -> Optional[User]:
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def create_user(
    db: AsyncSession,
    username: str,
    email: str,
    password: str,
    tier: str = "free",
) -> User:
    """Create a new user with hashed password."""
    user = User(
        username=username,
        email=email,
        hashed_password=pwd_context.hash(password),
        tier=tier,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


# ====== API KEY CRUD ======

async def create_api_key(
    db: AsyncSession,
    user_id,
    name: str,
    daily_limit: int = 100,
) -> tuple[APIKey, str]:
    """
    Create a new API key. Returns (key_record, plaintext_key).
    Plaintext is only available at creation — store it securely!
    """
    # Generate secure random key
    plaintext_key = f"sk_live_{secrets.token_urlsafe(32)}"
    key_prefix = plaintext_key[:12]  # sk_live_abc1... (for identification)
    key_hash = pwd_context.hash(plaintext_key)
    
    api_key = APIKey(
        user_id=user_id,
        key_hash=key_hash,
        key_prefix=key_prefix,
        name=name,
        daily_limit=daily_limit,
    )
    db.add(api_key)
    await db.commit()
    await db.refresh(api_key)
    
    return api_key, plaintext_key


async def find_api_key(db: AsyncSession, plaintext_key: str) -> Optional[APIKey]:
    """
    Find an API key by plaintext value.
    
    Since we store HASHES, we can't query directly. We need to:
    1. Get all active keys with the same prefix (for narrowing)
    2. Verify each one against the plaintext
    
    In production with millions of keys, add a lookup index.
    """
    key_prefix = plaintext_key[:12] if len(plaintext_key) >= 12 else plaintext_key
    
    # Get candidates by prefix (fast, indexed)
    result = await db.execute(
        select(APIKey)
        .where(APIKey.key_prefix == key_prefix, APIKey.is_active == True)
        .options(selectinload(APIKey.user))
    )
    candidates = result.scalars().all()
    
    # Verify against hash
    for candidate in candidates:
        if pwd_context.verify(plaintext_key, candidate.key_hash):
            # Update last_used_at
            candidate.last_used_at = datetime.now(timezone.utc)
            await db.commit()
            return candidate
    
    return None


async def list_user_api_keys(db: AsyncSession, user_id) -> list[APIKey]:
    """List all API keys for a user (no plaintext, only metadata)."""
    result = await db.execute(
        select(APIKey)
        .where(APIKey.user_id == user_id)
        .order_by(APIKey.created_at.desc())
    )
    return list(result.scalars().all())


async def revoke_api_key(db: AsyncSession, key_id, user_id) -> bool:
    """Revoke an API key (soft delete via is_active=False)."""
    result = await db.execute(
        update(APIKey)
        .where(APIKey.id == key_id, APIKey.user_id == user_id)
        .values(is_active=False)
    )
    await db.commit()
    return result.rowcount > 0


# ====== CONVERSATION CRUD ======

async def create_conversation(
    db: AsyncSession,
    user_id,
    title: str = "New Conversation",
    mode: str = "general",
) -> Conversation:
    conv = Conversation(user_id=user_id, title=title, mode=mode)
    db.add(conv)
    await db.commit()
    await db.refresh(conv)
    return conv


async def get_conversation(
    db: AsyncSession,
    conversation_id,
    user_id,
) -> Optional[Conversation]:
    """Get conversation with its messages, enforcing user ownership."""
    result = await db.execute(
        select(Conversation)
        .where(Conversation.id == conversation_id, Conversation.user_id == user_id)
        .options(selectinload(Conversation.messages))
    )
    return result.scalar_one_or_none()


async def list_user_conversations(
    db: AsyncSession,
    user_id,
    limit: int = 20,
) -> list[Conversation]:
    """List a user's conversations, most recent first."""
    result = await db.execute(
        select(Conversation)
        .where(Conversation.user_id == user_id)
        .order_by(Conversation.updated_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def add_message(
    db: AsyncSession,
    conversation_id,
    role: str,
    content: str,
    model: Optional[str] = None,
    input_tokens: Optional[int] = None,
    output_tokens: Optional[int] = None,
    cost_usd: Optional[str] = None,
) -> Message:
    """Add a message to a conversation."""
    message = Message(
        conversation_id=conversation_id,
        role=role,
        content=content,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost_usd,
    )
    db.add(message)
    await db.commit()
    await db.refresh(message)
    return message


async def get_conversation_history(
    db: AsyncSession,
    conversation_id,
    limit: int = 10,
) -> list[Message]:
    """Get the last N messages for a conversation (for sliding window)."""
    result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc())
        .limit(limit)
    )
    messages = list(result.scalars().all())
    return list(reversed(messages))  # oldest first


# ====== USAGE STATS ======

async def count_calls_today(db: AsyncSession, user_id) -> int:
    """Count messages sent by user today (for daily quota)."""
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    
    result = await db.execute(
        select(func.count(Message.id))
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(
            Conversation.user_id == user_id,
            Message.role == "user",
            Message.created_at >= today,
        )
    )
    return result.scalar() or 0