"""
분석 요청/중간 결과 스키마
"""
import uuid
from datetime import date
from typing import Optional, List, Literal

from pydantic import BaseModel, Field


class DateRange(BaseModel):
    start: date = Field(..., example="2024-03-01")
    end: date = Field(..., example="2024-03-31")


class AnalysisRequest(BaseModel):
    """POST /api/v1/analyze 요청 스키마"""
    query: str = Field(..., example="최근 평일 점심 매출이 왜 떨어졌나요?")
    mode: Literal["quick", "deep"] = Field("deep", example="deep")
    store_id: uuid.UUID
    file_id: Optional[uuid.UUID] = Field(None, description="업로드된 CSV UUID")
    date_range: Optional[DateRange] = None


class CorrelationResult(BaseModel):
    """상관분석 중간 결과"""
    variable_x: str
    variable_y: str
    r_value: float          # 피어슨 상관계수
    p_value: float          # 유의확률
    is_significant: bool    # p < 0.05
    interpretation: str     # "강한 양의 상관", "약한 음의 상관" 등


class TrendBreakResult(BaseModel):
    """추세 급변 탐지 결과"""
    break_date: Optional[date]
    before_avg: float
    after_avg: float
    change_rate: float      # 변화율 (%)


class InterpolationResult(BaseModel):
    """보간 추정 결과"""
    field_name: str
    estimated_value: float
    confidence: Literal["high", "medium", "low"]
    method: str
    disclaimer: str


class AnalysisResult(BaseModel):
    """에이전트 분석 중간/최종 결과 집합"""
    store_id: uuid.UUID
    date_range: Optional[DateRange]

    # 내부 데이터 분석
    sales_summary: Optional[dict] = None
    trend_break: Optional[TrendBreakResult] = None

    # 외부 데이터
    weather_data: Optional[dict] = None
    price_index_data: Optional[dict] = None
    subway_data: Optional[dict] = None

    # 보간 결과
    interpolations: List[InterpolationResult] = []

    # RAG 검색 결과
    rag_contexts: List[str] = []

    # 통계 분석
    correlations: List[CorrelationResult] = []
    statistical_summary: Optional[str] = None

    # 메타
    retry_count: int = 0
    is_sufficient: bool = False
