import asyncio
import os
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

load_dotenv()

async def test():
    db_url = os.getenv("DATABASE_URL")
    engine = create_async_engine(db_url, echo=False)
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        print("✅ DB CONNECTION SUCCESSFUL")
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"❌ DB ERROR: {e}")

if __name__ == "__main__":
    asyncio.run(test())
