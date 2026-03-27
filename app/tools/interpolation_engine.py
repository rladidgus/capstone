"""
실시간 데이터가 없을 때 과거 패턴 + 날씨 보정 계수로 통계적 추정치를 생성합니다.
"""
from typing import Optional

from app.agent.state import AgentState

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


def _get_season(month: int) -> str:
    if month in (3, 4, 5):
        return "spring"
    elif month in (6, 7, 8):
        return "summer"
    elif month in (9, 10, 11):
        return "fall"
    return "winter"


def get_historical_average_population(location: str, day_of_week: str, hour: int) -> float:
    """
    과거 동일 요일·시간대 평균 유동인구를 반환합니다.
    실제 구현에서는 Supabase에서 집계 데이터를 조회합니다.
    """
    # TODO: Supabase에서 historical 유동인구 데이터 조회
    baseline_map = {
        "monday": 3000, "tuesday": 3200, "wednesday": 3100,
        "thursday": 3300, "friday": 3800, "saturday": 4500, "sunday": 4000,
    }
    return float(baseline_map.get(day_of_week.lower(), 3000))


def estimate_population(location: str, date: str, weather: str) -> dict:
    """
    예상 유동인구 = 과거 요일 평균 × 날씨 보정 × 계절 보정

    Returns:
        {
          "estimated_value": int,
          "confidence": "medium",
          "method": "historical_avg_x_weather",
          "disclaimer": str
        }
    """
    from datetime import datetime
    if not date:
        dt = datetime.now()
    else:
        try:
            dt = datetime.fromisoformat(date)
        except ValueError:
            dt = datetime.now()
    day_name = dt.strftime("%A").lower()
    season = _get_season(dt.month)

    baseline = get_historical_average_population(location, day_name, dt.hour)
    weather_coeff = WEATHER_CORRECTION.get(weather.lower(), 1.0)
    season_coeff = SEASON_CORRECTION.get(season, 1.0)
    estimated = int(baseline * weather_coeff * season_coeff)

    return {
        "estimated_value": estimated,
        "confidence": "medium",
        "method": "historical_avg_x_weather_x_season",
        "disclaimer": "실시간 데이터가 아직 집계되지 않아, 과거 패턴과 오늘 날씨를 기반으로 통계적으로 추정된 결과입니다.",
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

    estimated = estimate_population(
        location="",
        date=start_date,
        weather=weather_condition,
    )

    return {
        "estimated_data": {"population_flow": estimated},
        "tool_calls": [{"tool": "interpolation_engine", "field": "population_flow"}],
    }
