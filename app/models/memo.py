"""
경영 메모 엔티티 — Pinecone 벡터 DB와 연동
"""
import uuid
from datetime import datetime, date
from typing import Optional, List

from pydantic import BaseModel, Field
from sqlalchemy import Column, String, DateTime, Date, Text, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.database import Base


# ── SQLAlchemy ORM 모델 ────────────────────────────────────────────

class MemoORM(Base):
    __tablename__ = "memos"

    memo_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id = Column(UUID(as_uuid=True), ForeignKey("stores.id"), nullable=False)

    memo_date = Column(Date, nullable=False, index=True)    # 메모 날짜
    title = Column(String, nullable=True)
    content = Column(Text, nullable=False)                  # 메모 본문
    tags = Column(JSON, default=list)                       # ["경쟁점포", "날씨", ...]

    vector_id = Column(String, nullable=True)               # Pinecone 벡터 ID
    is_embedded = Column(String, default="pending")         # pending | done | failed

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    store = relationship("StoreORM", back_populates="memos")


# ── Pydantic 스키마 ────────────────────────────────────────────────

class Memo(BaseModel):
    id: uuid.UUID
    store_id: uuid.UUID
    memo_date: date
    title: Optional[str]
    content: str
    tags: List[str] = []
    is_embedded: str
    created_at: datetime

    class Config:
        from_attributes = True


class MemoCreate(BaseModel):
    store_id: Optional[uuid.UUID] = None
    memo_date: date = Field(..., example="2024-03-13")
    title: Optional[str] = Field(None, example="근처 식당 오픈")
    content: str = Field(..., example="3월 13일 — 근처 ○○식당 오픈")
    tags: List[str] = Field(default_factory=list, example=["경쟁점포", "상권변화"])


class MemoUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    tags: Optional[List[str]] = None


class MemoSearchResult(BaseModel):
    """RAG 검색 결과"""
    memo_id: uuid.UUID
    memo_date: date
    content: str
    similarity_score: float
    tags: List[str] = []
