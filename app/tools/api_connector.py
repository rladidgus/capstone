"""
외부 공공 데이터를 수집합니다. 실패 시 보간 엔진으로 자동 fallback.
"""
import asyncio
from typing import Optional

import httpx

from app.agent.state import AgentState
import os

API_ENDPOINTS = {
    "weather":     "https://api.openweathermap.org/data/2.5/history/city",
    "price_index": "https://ecos.bok.or.kr/api/StatisticSearch",
    "subway":      "https://data.seoul.go.kr/api/rest/subwayHist",
    "living_idx":  "https://apis.data.go.kr/1360000/LivingWthrIdxServiceV4",
}


async def _fetch_weather(location: str, date: str) -> Optional[dict]:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                API_ENDPOINTS["weather"],
                params={
                    "q": location,
                    "dt": date,
                    "appid": os.getenv("OPENWEATHER_API_KEY", ""),
                    "lang": "kr",
                    "units": "metric",
                },
            )
            return resp.json() if resp.status_code == 200 else None
    except Exception:
        return None


async def _fetch_price_index(date: str) -> Optional[dict]:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                API_ENDPOINTS["price_index"],
                params={
                    "KEY": os.getenv("BOK_API_KEY", ""),
                    "Type": "json",
                    "STAT_CODE": "021Y204",
                    "START_TIME": date[:7].replace("-", ""),
                    "END_TIME": date[:7].replace("-", ""),
                },
            )
            return resp.json() if resp.status_code == 200 else None
    except Exception:
        return None


async def _fetch_subway(station: str, date: str) -> Optional[dict]:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                API_ENDPOINTS["subway"],
                params={"KEY": os.getenv("SEOUL_API_KEY", ""), "STATION_NM": station, "USE_DT": date},
            )
            return resp.json() if resp.status_code == 200 else None
    except Exception:
        return None


async def fetch_external_data(state: AgentState) -> AgentState:
    date_range = state.get("date_range", {})
    start_date = date_range.get("start", "") if date_range else ""
    location = ""  # store location은 서비스 레이어에서 주입

    weather, price, subway = await asyncio.gather(
        _fetch_weather(location, start_date),
        _fetch_price_index(start_date),
        _fetch_subway(location, start_date),
    )

    missing_fields = []
    if subway is None:
        missing_fields.append("population_flow")

    external_data = {
        "weather": weather,
        "price_index": price,
        "subway": subway,
        "missing_fields": missing_fields,
    }

    return {
        "external_data": external_data,
        "tool_calls": [{"tool": "api_connector", "missing": missing_fields}],
    }
