import os
from dotenv import load_dotenv
load_dotenv()

import asyncio
from app.db.database import init_db
from app.models.user import UserORM, StoreORM
from app.models.memo import MemoORM
from app.models.report import ReportORM
from app.models.sales import SalesRecordORM, SalesUploadORM

async def run():
    print("Testing DB Connection...")
    await init_db()

if __name__ == "__main__":
    asyncio.run(run())
