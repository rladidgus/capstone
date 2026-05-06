"""
실시간 데이터가 없을 때 과거 패턴 + 날씨 보정 계수로 통계적 추정치를 생성합니다.
"""
from datetime import datetime

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

# day_of_week 문자열 → 정수 (SalesRecordORM.day_of_week: 0=월요일)
DAY_NAME_TO_INT = {
    "monday": 0, "tuesday": 1, "wednesday": 2,
    "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6,
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


async def get_historical_average_sales(store_id: str, day_of_week: int) -> tuple[float, bool]:
    """
    Supabase에서 가게의 특정 요일 평균 매출을 조회합니다.

    Returns:
        (평균 매출액, 실제 데이터 여부)
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
                return float(avg), True
    except Exception:
        pass

    return float(FALLBACK_DAILY_SALES.get(day_of_week, 380_000)), False


async def estimate_population(store_id: str, date: str, weather: str) -> dict:
    """
    예상 활동지수 = 가게 과거 요일 평균 매출 × 날씨 보정 × 계절 보정

    실시간 지하철 데이터가 없을 때 상대적 활동 수준을 추정합니다.
    반환값은 실제 유동인구 수가 아닌 매출 기반 활동 지수입니다.
    """
    if not date:
        dt = datetime.now()
    else:
        try:
            dt = datetime.fromisoformat(date)
        except ValueError:
            dt = datetime.now()

    day_name = dt.strftime("%A").lower()
    day_int = DAY_NAME_TO_INT.get(day_name, 0)
    season = _get_season(dt.month)

    baseline, from_real_data = await get_historical_average_sales(store_id, day_int)
    weather_coeff = WEATHER_CORRECTION.get(weather.lower(), 1.0)
    season_coeff = SEASON_CORRECTION.get(season, 1.0)
    estimated = int(baseline * weather_coeff * season_coeff)

    disclaimer = (
        "가게의 과거 요일별 평균 매출과 날씨·계절 보정을 적용한 활동 지수입니다."
        if from_real_data
        else "가게 데이터 부족으로 서울 평균 기준값과 날씨·계절 보정을 적용한 추정치입니다."
    )

    return {
        "estimated_value": estimated,
        "confidence": "medium" if from_real_data else "low",
        "method": "store_historical_avg_x_weather_x_season" if from_real_data else "seoul_avg_x_weather_x_season",
        "disclaimer": disclaimer,
    }


async def run_interpolation(state: AgentState) -> AgentState:
    external = state.get("external_data") or {}
    missing_fields = external.get("missing_fields", [])

    if "population_flow" not in missing_fields:
        return state

    date_range = state.get("date_range") or {}
    start_date = date_range.get("start", "")
    weather_data = external.get("weather") or {}
    weather_condition = weather_data.get("condition", "cloudy")
    store_id = state.get("store_id", "")

    estimated = await estimate_population(
        store_id=store_id,
        date=start_date,
        weather=weather_condition,
    )

    return {
        "estimated_data": {"population_flow": estimated},
        "tool_calls": [{"tool": "interpolation_engine", "field": "population_flow"}],
    }
