# ============================================
# Wait for database to be ready before starting
# Retries connection with backoff
# ============================================
import asyncio
import sys
import time
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from config import DATABASE_URL


async def wait_for_db(max_attempts: int = 30, delay: float = 2.0) -> bool:
    """
    Try to connect to database, retry if it fails.
    Returns True if connected, False after max_attempts.
    """
    print(f"[wait_for_db] Attempting to connect to database...")
    print(f"[wait_for_db] Max attempts: {max_attempts}, delay: {delay}s")
    
    engine = create_async_engine(DATABASE_URL)
    
    for attempt in range(1, max_attempts + 1):
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
                await conn.commit()
            
            print(f"[wait_for_db] ✅ Database ready (attempt {attempt}/{max_attempts})")
            await engine.dispose()
            return True
            
        except Exception as e:
            error_type = type(e).__name__
            print(f"[wait_for_db] ⏳ Attempt {attempt}/{max_attempts} failed: {error_type}")
            
            if attempt < max_attempts:
                time.sleep(delay)
    
    print(f"[wait_for_db] ❌ Database not ready after {max_attempts} attempts")
    await engine.dispose()
    return False


if __name__ == "__main__":
    result = asyncio.run(wait_for_db())
    sys.exit(0 if result else 1)
