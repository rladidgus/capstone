from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

import os


class Base(DeclarativeBase):
    pass


from sqlalchemy.pool import NullPool

database_url = os.getenv("DATABASE_URL", "")
engine = create_async_engine(
    database_url, 
    echo=False,
    poolclass=NullPool,      # 커넥션 풀을 사용하지 않고 요청마다 새 연결을 맺어 끊김 문제 원천 차단
    connect_args={
        "statement_cache_size": 0,
        "prepared_statement_cache_size": 0
    }
)

AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def init_db():
    # 모든 ORM 모델이 Base.metadata에 등록되도록 명시적으로 import
    from app.models import user, memo, sales, report  # noqa: F401

    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        print("✅ 데이터베이스 초기화 성공")
    except Exception as e:
        print(f"❌ 데이터베이스 연결 실패: {e}")
        raise


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
