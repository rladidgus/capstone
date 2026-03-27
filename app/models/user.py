"""
사용자 및 가게 관련 엔티티
"""
import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy import Column, String, DateTime, ForeignKey, Float
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.database import Base


# ── SQLAlchemy ORM 모델 ────────────────────────────────────────────

class UserORM(Base):
    __tablename__ = "users"

    user_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    stores = relationship("StoreORM", back_populates="user", cascade="all, delete-orphan")


class StoreORM(Base):
    __tablename__ = "stores"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    name = Column(String, nullable=False)
    district = Column(String, nullable=False)       # 예: 마포구
    station = Column(String, nullable=True)         # 예: 홍대입구역
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("UserORM", back_populates="stores")
    sales = relationship("SalesRecordORM", back_populates="store", cascade="all, delete-orphan")
    memos = relationship("MemoORM", back_populates="store", cascade="all, delete-orphan")
    reports = relationship("ReportORM", back_populates="store", cascade="all, delete-orphan")


# ── Pydantic 스키마 ────────────────────────────────────────────────

class Location(BaseModel):
    district: str = Field(..., example="마포구")
    station: Optional[str] = Field(None, example="홍대입구역")
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class User(BaseModel):
    id: uuid.UUID
    email: str
    created_at: datetime

    class Config:
        from_attributes = True


class Store(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    location: Location
    created_at: datetime

    class Config:
        from_attributes = True


class StoreCreate(BaseModel):
    name: str = Field(..., example="홍대 짬뽕맛집")
    location: Location


class StoreSetupRequest(BaseModel):
    """POST /auth/setup 요청 스키마"""
    user_id: str = Field(..., example="user-123")
    store_name: str = Field(..., example="홍대 짬뽕맛집")
    location: Location

class StoreSetupResponse(BaseModel):
    """POST /auth/setup 응답 스키마"""
    message: str = Field(..., example="가게 설정(온보딩)이 완료되었습니다!")
    store_id: str = Field(..., example="123e4567-e89b-12d3-a456-426614174000")
    store_name: str = Field(..., example="홍대 짬뽕맛집")
