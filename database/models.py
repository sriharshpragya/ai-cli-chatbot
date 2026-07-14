# ============================================
# SQLAlchemy Models — Database Schema
# Uses async-compatible declarative style
# ============================================
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Integer, DateTime, Boolean, 
    ForeignKey, Text, Index, func
)
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy.dialects.postgresql import UUID
import uuid


class Base(DeclarativeBase):
    """All models inherit from this. Like ActiveRecord::Base."""
    pass


def utc_now():
    """Helper for default timestamps."""
    return datetime.now(timezone.utc)


# ====== USERS TABLE ======

class User(Base):
    __tablename__ = "users"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    tier = Column(String(20), nullable=False, default="free")  # free, paid, admin
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )
    
    # Relationships
    api_keys = relationship("APIKey", back_populates="user", cascade="all, delete-orphan")
    conversations = relationship("Conversation", back_populates="user", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<User {self.username} ({self.tier})>"


# ====== API KEYS TABLE ======

class APIKey(Base):
    __tablename__ = "api_keys"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Key data
    key_hash = Column(String(255), unique=True, nullable=False, index=True)  # hashed, never plaintext
    key_prefix = Column(String(20), nullable=False)  # first 8 chars for identification (sk_live_...)
    name = Column(String(100), nullable=False)  # user-provided label ("Dev", "Prod")
    
    # Metadata
    is_active = Column(Boolean, nullable=False, default=True)
    daily_limit = Column(Integer, nullable=False, default=100)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)  # optional expiration
    
    # Relationships
    user = relationship("User", back_populates="api_keys")
    
    def __repr__(self):
        return f"<APIKey {self.key_prefix}... name={self.name}>"


# ====== CONVERSATIONS TABLE ======

class Conversation(Base):
    __tablename__ = "conversations"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    
    title = Column(String(200), nullable=False, default="New Conversation")
    mode = Column(String(50), nullable=False, default="general")  # ruby, python, sql, general, code-review
    
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )
    
    # Relationships
    user = relationship("User", back_populates="conversations")
    messages = relationship(
        "Message",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.created_at",
    )
    
    def __repr__(self):
        return f"<Conversation {self.title} ({len(self.messages)} msgs)>"


# ====== MESSAGES TABLE ======

class Message(Base):
    __tablename__ = "messages"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id = Column(UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    
    role = Column(String(20), nullable=False)  # 'user', 'assistant', 'system'
    content = Column(Text, nullable=False)
    
    # Cost tracking (from Day 11)
    model = Column(String(100), nullable=True)  # which model generated this
    input_tokens = Column(Integer, nullable=True)
    output_tokens = Column(Integer, nullable=True)
    cost_usd = Column(String(20), nullable=True)  # stored as string to preserve precision
    
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, index=True)
    
    # Relationships
    conversation = relationship("Conversation", back_populates="messages")
    
    def __repr__(self):
        return f"<Message {self.role}: {self.content[:50]}...>"


# ====== INDEXES ======
# Composite indexes for common queries

Index(
    "idx_conversations_user_updated",
    Conversation.user_id,
    Conversation.updated_at.desc(),
)

Index(
    "idx_messages_conversation_created",
    Message.conversation_id,
    Message.created_at,
)