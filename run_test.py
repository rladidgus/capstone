import os
from dotenv import load_dotenv
load_dotenv()
import asyncio
from app.db.database import init_db

asyncio.run(init_db())
