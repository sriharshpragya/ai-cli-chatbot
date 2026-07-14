# ============================================
# Bootstrap script - create user + API key
# ============================================
import asyncio
from database.session import AsyncSessionLocal
from database import crud


USERNAME = "pragya"
EMAIL = "pragya@example.com"
PASSWORD = "change-me-securely"


async def main():
    async with AsyncSessionLocal() as db:
        user = await crud.get_user_by_username(db, USERNAME)
        if not user:
            print(f"Creating user: {USERNAME}")
            user = await crud.create_user(
                db,
                username=USERNAME,
                email=EMAIL,
                password=PASSWORD,
                tier="paid",
            )
            print(f"✅ Created user: {user}")
        else:
            print(f"📌 User already exists: {user}")
        
        key_record, plaintext = await crud.create_api_key(
            db,
            user_id=user.id,
            name="Bootstrap Testing Key",
            daily_limit=1000,
        )
        
        print(f"\n🔑 Your API key (SAVE THIS NOW):")
        print(f"   {plaintext}")


asyncio.run(main())
