"""
실시간 데이터가 없을 때 과거 패턴 + 날씨 보정 계수로 통계적 추정치를 생성합니다.
"""
from datetime import date as date_type, datetime, timedelta

from sqlalchemy import select, func

from app.agent.state import AgentState
from app.db.database import AsyncSessionLocal
from app.models.sales import SalesRecordORM

WEATHER_CORRECTION = {
    "rainy":  0.70,
    "cloudy": 0.90,
    "sunny":  1.10,
    "snow":   0.50,
}

SEASON_CORRECTION = {
    "spring": 1.05,
    "summer": 0.95,
    "fall":   1.05,
    "winter": 0.88,
}

# 데이터 없을 때 사용하는 서울 평균 요일별 매출 기준값 (원)
FALLBACK_DAILY_SALES = {
    0: 350_000, 1: 370_000, 2: 360_000,
    3: 380_000, 4: 450_000, 5: 520_000, 6: 480_000,
}


def _get_season(month: int) -> str:
    if month in (3, 4, 5):
        return "spring"
    elif month in (6, 7, 8):
        return "summer"
    elif month in (9, 10, 11):
        return "fall"
    return "winter"


async def get_historical_average_sales(store_id: str, day_of_week: int) -> tuple[float, bool, str]:
    """
    Supabase에서 가게의 특정 요일 평균 매출을 조회합니다.

    Returns:
        (평균 매출액, 실제 데이터 여부, fallback 사유)
        실제 데이터가 없으면 서울 평균 fallback 값과 False를 반환합니다.
    """
    try:
        import uuid
        store_uuid = uuid.UUID(store_id)
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(func.avg(SalesRecordORM.amount))
                .where(SalesRecordORM.store_id == store_uuid)
                .where(SalesRecordORM.day_of_week == day_of_week)
            )
            avg = result.scalar()
            if avg is not None:
                return float(avg), True, "store_historical_sales"
            return float(FALLBACK_DAILY_SALES.get(day_of_week, 380_000)), False, "no_historical_sales"
    except Exception as exc:
        return float(FALLBACK_DAILY_SALES.get(day_of_week, 380_000)), False, f"db_error:{type(exc).__name__}"


def _parse_date(value: str) -> date_type:
    if not value:
        return datetime.now().date()
    try:
        return datetime.fromisoformat(value).date()
    except ValueError:
        return datetime.now().date()


def _iter_dates(start: date_type, end: date_type) -> list[date_type]:
    if end < start:
        return [start]
    return [start + timedelta(days=offset) for offset in range((end - start).days + 1)]


def _calculate_activity_index(baseline: float, weather: str, month: int) -> tuple[int, str, float, float]:
    season = _get_season(month)
    weather_coeff = WEATHER_CORRECTION.get(weather.lower(), 1.0)
    season_coeff = SEASON_CORRECTION.get(season, 1.0)
    estimated = int(baseline * weather_coeff * season_coeff)
    return estimated, season, weather_coeff, season_coeff


async def estimate_business_activity_for_day(store_id: str, target_date: date_type, weather: str) -> dict:
    day_int = target_date.weekday()
    baseline, from_real_data, fallback_reason = await get_historical_average_sales(store_id, day_int)
    estimated, season, weather_coeff, season_coeff = _calculate_activity_index(
        baseline=baseline,
        weather=weather,
        month=target_date.month,
    )

    return {
        "date": target_date.isoformat(),
        "estimated_value": estimated,
        "baseline_sales": round(baseline, 2),
        "used_store_history": from_real_data,
        "fallback_reason": None if from_real_data else fallback_reason,
        "day_of_week": day_int,
        "season": season,
        "weather": weather,
        "weather_coefficient": weather_coeff,
        "season_coefficient": season_coeff,
    }


async def estimate_business_activity_index(store_id: str, start_date: str, end_date: str, weather: str) -> dict:
    """
    예상 활동지수 = 가게 과거 요일 평균 매출 × 날씨 보정 × 계절 보정

    실시간 지하철 데이터가 없을 때 상대적 활동 수준을 추정합니다.
    반환값은 실제 유동인구 수가 아닌 매출 기반 활동 지수입니다.
    """
    start = _parse_date(start_date)
    end = _parse_date(end_date) if end_date else start
    dates = _iter_dates(start, end)
    daily = [
        await estimate_business_activity_for_day(store_id, target_date, weather)
        for target_date in dates
    ]

    total_value = sum(item["estimated_value"] for item in daily)
    avg_value = round(total_value / len(daily), 2) if daily else 0
    used_history_count = sum(1 for item in daily if item["used_store_history"])
    if daily and used_history_count == len(daily):
        confidence = "medium"
    elif used_history_count:
        confidence = "low"
    else:
        confidence = "low"

    disclaimer = (
        "실제 유동인구 수가 아니라 가게 과거 매출 패턴에 날씨·계절 보정을 적용한 활동 지수입니다. "
        "명 단위 인구 수처럼 해석하지 말고, 외부 유동인구 데이터가 없을 때의 보조 지표로만 사용하세요."
    )

    return {
        "estimated_value": avg_value,
        "avg_daily_value": avg_value,
        "total_value": total_value,
        "unit": "activity_index",
        "is_actual_population": False,
        "source": "interpolation_engine",
        "fallback_for": "population_flow",
        "replacement_type": "business_activity_index",
        "confidence": confidence,
        "method": "historical_sales_x_weather_x_season",
        "period_start": start.isoformat(),
        "period_end": end.isoformat(),
        "days_count": len(daily),
        "used_store_history_days": used_history_count,
        "daily": daily,
        "disclaimer": disclaimer,
    }


async def run_interpolation(state: AgentState) -> AgentState:
    external = state.get("external_data") or {}
    missing_fields = external.get("missing_fields", [])

    if "population_flow" not in missing_fields:
        return state

    date_range = state.get("date_range") or {}
    start_date = date_range.get("start", "")
    end_date = date_range.get("end", "")
    weather_data = external.get("weather") or {}
    weather_condition = weather_data.get("condition", "cloudy")
    store_id = state.get("store_id", "")

    estimated = await estimate_business_activity_index(
        store_id=store_id,
        start_date=start_date,
        end_date=end_date,
        weather=weather_condition,
    )

    return {
        "estimated_data": {
            "population_flow": estimated,
            "business_activity_index": estimated,
        },
        "tool_calls": [
            {
                "tool": "interpolation_engine",
                "field": "population_flow",
                "replacement_type": "business_activity_index",
            }
        ],
    }
