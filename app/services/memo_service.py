"""
경영 메모 임베딩 및 Pinecone 저장 서비스
"""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.vector_store import get_pinecone_index
from app.models.memo import MemoORM, MemoCreate
from app.services.llm_service import LLMService

llm = LLMService()


class MemoService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_memo(self, data: MemoCreate) -> MemoORM:
        memo = MemoORM(**data.model_dump())
        self.db.add(memo)
        await self.db.commit()
        await self.db.refresh(memo)
        await self._embed_and_store(memo)
        return memo

    async def _embed_and_store(self, memo: MemoORM) -> None:
        """메모를 벡터화하여 Pinecone에 저장합니다."""
        text = f"{memo.memo_date} {memo.title or ''} {memo.content}"
        try:
            vector = await llm.embed(text)
            index = get_pinecone_index()
            vector_id = str(memo.id)
            index.upsert(vectors=[
                {
                    "id": vector_id,
                    "values": vector,
                    "metadata": {
                        "store_id": str(memo.store_id),
                        "date": str(memo.memo_date),
                        "content": memo.content,
                        "tags": memo.tags or [],
                    },
                }
            ])
            memo.vector_id = vector_id
            memo.is_embedded = "done"
        except Exception:
            memo.is_embedded = "failed"
        finally:
            await self.db.commit()

    async def delete_memo(self, memo_id: uuid.UUID, store_id: uuid.UUID) -> None:
        result = await self.db.execute(select(MemoORM).where(MemoORM.id == memo_id))
        memo = result.scalar_one_or_none()
        if memo and memo.store_id == store_id:
            if memo.vector_id:
                get_pinecone_index().delete(ids=[memo.vector_id])
            await self.db.delete(memo)
            await self.db.commit()

    async def list_memos(self, store_id: uuid.UUID) -> list[MemoORM]:
        result = await self.db.execute(
            select(MemoORM).where(MemoORM.store_id == store_id).order_by(MemoORM.memo_date.desc())
        )
        return list(result.scalars().all())
