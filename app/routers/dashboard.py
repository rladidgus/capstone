import uuid
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.db.database import get_db
from app.routers.auth import get_current_store
from app.models.sales import SalesRecordORM
from app.models.report import ReportORM
from app.models.user import StoreORM
from app.tools.api_connector import fetch_external_data
from app.tools.interpolation_engine import estimate_business_activity_index

router = APIRouter()


def _extract_from_latest_report(report: ReportORM | None) -> dict[str, Any] | None:
    if not report:
        return None

    chart = report.chart_data or {}
    if isinstance(chart, dict):
        for series in chart.get("series", []):
            if not isinstance(series, dict):
                continue
            name = str(series.get("name", ""))
            data = series.get("data", [])
            if data and ("유동" in name or "활동" in name):
                return {
                    "value": data[-1],
                    "source": "latest_report_chart",
                    "label": name,
                    "is_actual_population": "활동" not in name,
                }

    data = report.report_data or {}
    if isinstance(data, dict):
        quality = data.get("data_quality") or {}
        population = data.get("population_flow") or data.get("business_activity_index")
        if isinstance(population, dict):
            return {
                "value": population.get("total_passenger_count") or population.get("estimated_value"),
                "source": "latest_report_data",
                "label": population.get("replacement_type", "population_flow"),
                "is_actual_population": population.get("is_actual_population", True),
                "confidence": population.get("confidence") or quality.get("confidence"),
            }

    return None


def _extract_from_external_data(external_data: dict[str, Any]) -> dict[str, Any] | None:
    subway = external_data.get("subway")
    if isinstance(subway, dict) and subway.get("total_passenger_count") is not None:
        return {
            "value": subway["total_passenger_count"],
            "source": "seoul_subway_api",
            "label": "지하철 승하차 인원",
            "is_actual_population": True,
            "date_scope": subway.get("date_scope"),
            "days_collected": subway.get("days_collected"),
        }
    return None

@router.get("/summary")
async def get_dashboard_summary(
    db: AsyncSession = Depends(get_db),
    store_id: uuid.UUID = Depends(get_current_store),
):
    """가장 최근의 유동인구, 전날 매출 요약 등을 가볍게 조회"""
    # 가장 최근 매출 일자 확인
    recent_date_result = await db.execute(
        select(func.max(SalesRecordORM.sales_date))
        .where(SalesRecordORM.store_id == store_id)
    )
    recent_date = recent_date_result.scalar_one_or_none()
    
    recent_sales = 0
    recent_count = 0
    
    if recent_date:
        # 1. 최근일 총 매출
        sales_result = await db.execute(
            select(func.sum(SalesRecordORM.amount))
            .where(SalesRecordORM.store_id == store_id)
            .where(SalesRecordORM.sales_date == recent_date)
        )
        recent_sales = sales_result.scalar_one_or_none() or 0
        
        # 2. 최근일 총 건수
        count_result = await db.execute(
            select(func.sum(SalesRecordORM.quantity))
            .where(SalesRecordORM.store_id == store_id)
            .where(SalesRecordORM.sales_date == recent_date)
        )
        recent_count = count_result.scalar_one_or_none() or 0
    
    report_result = await db.execute(
        select(ReportORM)
        .where(ReportORM.store_id == store_id)
        .where(ReportORM.status == "completed")
        .order_by(ReportORM.completed_at.desc().nullslast(), ReportORM.created_at.desc())
        .limit(1)
    )
    latest_report = report_result.scalar_one_or_none()
    traffic_info = _extract_from_latest_report(latest_report)

    if traffic_info is None:
        store_result = await db.execute(select(StoreORM).where(StoreORM.id == store_id))
        store = store_result.scalar_one_or_none()
        if store and recent_date:
            state = {
                "user_query": "대시보드 최근 유동인구 요약",
                "store_id": str(store_id),
                "store_location": {
                    "district": store.district,
                    "station": store.station,
                    "lat": store.latitude,
                    "lng": store.longitude,
                },
                "uploaded_file_path": None,
                "mode": "quick",
                "date_range": {
                    "start": str(recent_date),
                    "end": str(recent_date),
                },
                "hypotheses": [],
                "analysis_plan": [],
                "tool_calls": [],
                "internal_data": None,
                "external_data": None,
                "estimated_data": None,
                "rag_context": None,
                "correlation_results": None,
                "statistical_summary": None,
                "final_report_json": None,
                "chart_data": None,
                "retry_count": 0,
                "is_sufficient": False,
            }
            external_state = await fetch_external_data(state)
            external_data = external_state.get("external_data") or {}
            traffic_info = _extract_from_external_data(external_data)

            if traffic_info is None:
                weather = external_data.get("weather") or {}
                activity = await estimate_business_activity_index(
                    store_id=str(store_id),
                    start_date=str(recent_date),
                    end_date=str(recent_date),
                    weather=weather.get("condition", "cloudy"),
                )
                traffic_info = {
                    "value": activity.get("estimated_value"),
                    "source": "interpolation_engine",
                    "label": "매출 기반 활동 지수",
                    "is_actual_population": False,
                    "confidence": activity.get("confidence"),
                    "unit": activity.get("unit"),
                }

    traffic_info = traffic_info or {
        "value": None,
        "source": "unavailable",
        "label": "유동인구 데이터 없음",
        "is_actual_population": False,
    }
    
    return {
        "recent_date": recent_date,
        "recent_sales": float(recent_sales),
        "recent_count": int(recent_count),
        "recent_foot_traffic": traffic_info["value"],
        "traffic_source": traffic_info["source"],
        "traffic_label": traffic_info["label"],
        "traffic_is_actual_population": traffic_info["is_actual_population"],
        "traffic_meta": {
            key: value
            for key, value in traffic_info.items()
            if key not in {"value", "source", "label", "is_actual_population"}
        },
    }
