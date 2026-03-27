"""
분석 리포트 출력 엔티티
"""
import uuid
from datetime import datetime, date
from typing import Optional, List, Literal

from pydantic import BaseModel, Field
from sqlalchemy import Column, String, DateTime, JSON, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.database import Base


# ── SQLAlchemy ORM 모델 ────────────────────────────────────────────

class ReportORM(Base):
    __tablename__ = "reports"

    report_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id = Column(UUID(as_uuid=True), ForeignKey("stores.id"), nullable=False)

    mode = Column(String, nullable=False)               # "quick" | "deep"
    user_query = Column(Text, nullable=False)
    status = Column(String, default="processing")       # processing | completed | failed

    # 데이터 품질
    realtime_available = Column(String, default="false")
    interpolated_fields = Column(JSON, default=list)
    confidence_level = Column(String, default="medium") # high | medium | low

    # 리포트 본문 (JSON 직렬화)
    report_data = Column(JSON, nullable=True)
    chart_data = Column(JSON, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    store = relationship("StoreORM", back_populates="reports")


# ── Pydantic 스키마 ────────────────────────────────────────────────

class AnalysisFactorDetail(BaseModel):
    factor: str = Field(..., example="날씨/유동인구")
    impact: Literal["긍정적", "부정적", "중립"] = "중립"
    description: str


class DataQuality(BaseModel):
    realtime_available: bool = False
    interpolated_fields: List[str] = Field(default_factory=list, example=["population_flow"])
    confidence: Literal["high", "medium", "low"] = "medium"


class ReportData(BaseModel):
    summary: str
    analysis_details: List[AnalysisFactorDetail] = []
    action_items: List[str] = []


class ChartSeries(BaseModel):
    name: str
    data: List[float]


class ChartData(BaseModel):
    type: str = Field(..., example="multi_line")
    categories: List[str]           # X축 레이블 (날짜 등)
    series: List[ChartSeries]


class Report(BaseModel):
    """GET /api/v1/reports/{id} 응답 스키마"""
    report_id: uuid.UUID
    status: str
    mode: str
    data_quality: DataQuality
    report_data: Optional[ReportData]
    chart_data: Optional[ChartData]
    created_at: datetime

    class Config:
        from_attributes = True


class ReportSummary(BaseModel):
    """리포트 목록 조회용 요약"""
    report_id: uuid.UUID
    mode: str
    user_query: str
    status: str
    confidence: str
    created_at: datetime

    class Config:
        from_attributes = True
