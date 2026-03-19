"""
매출 데이터 관련 엔티티
"""
import uuid
from datetime import datetime, date
from decimal import Decimal
from typing import Optional, List

from pydantic import BaseModel, Field
from sqlalchemy import Column, String, DateTime, Date, Numeric, Integer, ForeignKey, Enum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import enum

from app.db.database import Base


# ── Enum ──────────────────────────────────────────────────────────

class PaymentMethod(str, enum.Enum):
    cash = "cash"
    card = "card"
    delivery = "delivery"   # 배달 플랫폼
    other = "other"


class SalesChannel(str, enum.Enum):
    hall = "hall"           # 홀 (매장 내)
    takeout = "takeout"     # 포장
    delivery = "delivery"   # 배달


# ── SQLAlchemy ORM 모델 ────────────────────────────────────────────

class SalesRecordORM(Base):
    __tablename__ = "sales_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id = Column(UUID(as_uuid=True), ForeignKey("stores.id"), nullable=False)
    upload_id = Column(UUID(as_uuid=True), ForeignKey("sales_uploads.id"), nullable=True)

    sold_at = Column(DateTime, nullable=False, index=True)      # 판매 일시
    sales_date = Column(Date, nullable=False, index=True)       # 판매 날짜 (집계용)
    hour = Column(Integer, nullable=True)                       # 시간대 (0~23)
    day_of_week = Column(Integer, nullable=True)                # 요일 (0=월요일)

    amount = Column(Numeric(12, 2), nullable=False)             # 매출액 (원)
    quantity = Column(Integer, default=1)                       # 판매 수량
    menu_name = Column(String, nullable=True)                   # 메뉴명
    category = Column(String, nullable=True)                    # 메뉴 카테고리
    payment_method = Column(Enum(PaymentMethod), default=PaymentMethod.card)
    channel = Column(Enum(SalesChannel), default=SalesChannel.hall)

    created_at = Column(DateTime, default=datetime.utcnow)

    store = relationship("StoreORM", back_populates="sales")
    upload = relationship("SalesUploadORM", back_populates="records")


class SalesUploadORM(Base):
    """CSV/XLSX 업로드 파일 메타데이터"""
    __tablename__ = "sales_uploads"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id = Column(UUID(as_uuid=True), ForeignKey("stores.id"), nullable=False)
    file_name = Column(String, nullable=False)
    file_path = Column(String, nullable=False)                  # 로컬 저장 경로
    row_count = Column(Integer, default=0)
    status = Column(String, default="pending")                  # pending | processing | done | failed
    uploaded_at = Column(DateTime, default=datetime.utcnow)

    records = relationship("SalesRecordORM", back_populates="upload")


# ── Pydantic 스키마 ────────────────────────────────────────────────

class SalesRecord(BaseModel):
    id: uuid.UUID
    store_id: uuid.UUID
    sold_at: datetime
    amount: Decimal
    quantity: int
    menu_name: Optional[str]
    category: Optional[str]
    payment_method: PaymentMethod
    channel: SalesChannel

    class Config:
        from_attributes = True


class SalesUpload(BaseModel):
    id: uuid.UUID
    store_id: uuid.UUID
    file_name: str
    row_count: int
    status: str
    uploaded_at: datetime

    class Config:
        from_attributes = True


class SalesSummary(BaseModel):
    """집계된 매출 요약 (분석 입력용)"""
    store_id: uuid.UUID
    period_start: date
    period_end: date
    total_amount: Decimal
    avg_daily_amount: Decimal
    peak_hour: Optional[int]
    peak_day_of_week: Optional[int]
    top_menus: List[dict] = Field(default_factory=list)
    channel_breakdown: dict = Field(default_factory=dict)
    time_series: List[dict] = Field(default_factory=list)   # [{date, amount}, ...]
