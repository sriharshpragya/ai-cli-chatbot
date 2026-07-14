# ============================================
# Async database session management
# Gracefully handles missing DATABASE_URL (CLI mode)
# ============================================
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from config import DATABASE_URL, DATABASE_ENABLED


# Only create engine if DATABASE_URL is set
engine = None
AsyncSessionLocal = None

if DATABASE_ENABLED:
    engine = create_async_engine(
        DATABASE_URL,
        echo=False,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
    )
    
    AsyncSessionLocal = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


async def get_db() -> AsyncSession:
    """
    Dependency for FastAPI endpoints.
    Raises error if called when database is disabled.
    """
    if not DATABASE_ENABLED:
        raise RuntimeError(
            "Database not configured. Set DATABASE_URL to enable API mode."
        )
    
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
