"""Validate API connector date fallback behavior.

This script has two modes:
- default: deterministic unit checks without network calls
- --real: calls configured public APIs and prints a compact availability report
"""
import argparse
import asyncio
from datetime import date
import os
from pathlib import Path
import sys
from typing import Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

from app.tools import api_connector as api


def _daily(use_date: str, ride: int = 1000, alight: int = 900) -> dict[str, Any]:
    return {
        "source": "test",
        "station": "홍대입구역",
        "use_date": use_date,
        "date_scope": "day",
        "ride_passenger_count": ride,
        "alight_passenger_count": alight,
        "total_passenger_count": ride + alight,
        "lines": [],
    }


async def _run_scripted_subway_fetch(outputs: list[Optional[dict[str, Any]]]) -> Optional[dict]:
    original = api._fetch_subway_for_date
    scripted_outputs = list(outputs)

    async def fake_fetch_subway_for_date(client, api_key: str, station: str, target_date: date) -> Optional[dict]:
        if scripted_outputs:
            return scripted_outputs.pop(0)
        return None

    os.environ.setdefault("SEOUL_API_KEY", "test-key")
    api._fetch_subway_for_date = fake_fetch_subway_for_date
    try:
        return await api._fetch_subway("홍대입구역", "2026-05-06", "2026-05-06")
    finally:
        api._fetch_subway_for_date = original


async def validate_without_network() -> None:
    assert api._parse_iso_date("2026-05-06") == date(2026, 5, 6)
    assert api._parse_iso_date("bad-date") is None
    assert api._is_recent_or_current_date("") is True
    assert api._is_recent_or_current_date("2000-01-01") is False
    assert api._is_recent_or_current_date(api._today_kst().isoformat()) is True
    assert api._iter_dates(date(2026, 5, 6), date(2026, 5, 8)) == [
        date(2026, 5, 6),
        date(2026, 5, 7),
        date(2026, 5, 8),
    ]
    assert api._week_bounds(date(2026, 5, 6)) == (date(2026, 5, 4), date(2026, 5, 10))
    assert api._month_bounds(date(2026, 5, 6)) == (date(2026, 5, 1), date(2026, 5, 31))

    new_field_payload = {
        "CardSubwayStatsNew": {
            "row": [
                {
                    "USE_YMD": "20260420",
                    "SBWY_ROUT_LN_NM": "2호선",
                    "SBWY_STNS_NM": "홍대입구",
                    "GTON_TNOPE": "85000",
                    "GTOFF_TNOPE": "85518",
                    "REG_YMD": "20260423",
                },
            ]
        }
    }
    normalized = api._normalize_subway_data(new_field_payload, "홍대입구역", "20260420")
    assert normalized is not None
    assert normalized["total_passenger_count"] == 170518
    assert normalized["lines"][0]["line"] == "2호선"

    asos_normalized = api._normalize_asos_daily_rows(
        [
            {
                "tm": "2026-04-20",
                "stnId": "108",
                "stnNm": "서울",
                "avgTa": "15.2",
                "minTa": "10.1",
                "maxTa": "20.3",
                "sumRn": "3.5",
                "avgRhm": "68.4",
                "avgWs": "2.1",
                "avgTca": "7.0",
            }
        ],
        district="마포구",
        station_id="108",
        scope="exact",
    )
    assert asos_normalized is not None
    assert asos_normalized["source"] == "KMA ASOS daily observation"
    assert asos_normalized["date_scope"] == "exact"
    assert asos_normalized["condition"] == "rainy"
    assert asos_normalized["temperature_c"] == 15.2
    assert asos_normalized["rainfall_mm"] == 3.5

    original_asos_range = api._fetch_asos_daily_range
    asos_outputs = [None, None, asos_normalized]

    async def fake_fetch_asos_daily_range(*args, **kwargs):
        if asos_outputs:
            result = asos_outputs.pop(0)
            if result:
                result = {**result, "date_scope": kwargs.get("scope") or args[-1]}
            return result
        return None

    os.environ.setdefault("WATHER_DATA_LIST_API_KEY", "test-key")
    api._fetch_asos_daily_range = fake_fetch_asos_daily_range
    try:
        weather_fallback = await api._fetch_asos_daily_weather("마포구", "2026-05-06", "2026-05-06")
    finally:
        api._fetch_asos_daily_range = original_asos_range
    assert weather_fallback is not None
    assert weather_fallback["date_scope"] == "month"

    exact_result = await _run_scripted_subway_fetch([_daily("20260506")])
    assert exact_result is not None
    assert exact_result["date_scope"] == "exact"
    assert exact_result["days_collected"] == 1
    assert exact_result["total_passenger_count"] == 1900

    week_outputs = [None] + [
        None,
        _daily("20260505", 2000, 1800),
        _daily("20260506", 2100, 1900),
        None,
        None,
        None,
        None,
    ]
    week_result = await _run_scripted_subway_fetch(week_outputs)
    assert week_result is not None
    assert week_result["date_scope"] == "week"
    assert week_result["days_collected"] == 2
    assert week_result["total_passenger_count"] == 7800
    assert week_result["avg_daily_total_passenger_count"] == 3900

    month_outputs = [None] + [None] * 7 + [None] * 10 + [_daily("20260511", 3000, 2500)] + [None] * 20
    month_result = await _run_scripted_subway_fetch(month_outputs)
    assert month_result is not None
    assert month_result["date_scope"] == "month"
    assert month_result["days_collected"] == 1
    assert month_result["start_date"] == "20260511"

    empty_result = await _run_scripted_subway_fetch([None] * 40)
    assert empty_result is None

    print("fallback_unit_checks: OK")


def _summarize_external_data(label: str, result: dict[str, Any]) -> None:
    external_data = result.get("external_data", {})
    subway = external_data.get("subway")
    price = external_data.get("price_index")
    living_idx = external_data.get("living_idx")
    living_idx_status = external_data.get("living_idx_status")
    store_zone = external_data.get("store_zone")
    weather = external_data.get("weather")

    print(f"\n[{label}]")
    print("missing_fields:", external_data.get("missing_fields"))
    print("weather:", None if weather is None else {
        "source": weather.get("source"),
        "scope": weather.get("date_scope"),
        "start_date": weather.get("start_date"),
        "end_date": weather.get("end_date"),
        "condition": weather.get("condition"),
        "temperature_c": weather.get("temperature_c"),
        "rainfall_mm": weather.get("rainfall_mm"),
    })
    print("subway:", None if subway is None else {
        "scope": subway.get("date_scope"),
        "start_date": subway.get("start_date"),
        "end_date": subway.get("end_date"),
        "days_collected": subway.get("days_collected"),
        "total": subway.get("total_passenger_count"),
    })
    print("price_index:", None if price is None else {
        "start_month": price.get("start_month"),
        "end_month": price.get("end_month"),
        "indicators": sorted((price.get("indicators") or {}).keys()),
    })
    print("living_idx:", None if living_idx is None else {
        "time": living_idx.get("time"),
        "indexes": sorted((living_idx.get("indexes") or {}).keys()),
    })
    print("living_idx_status:", living_idx_status)
    print("store_zone:", None if store_zone is None else {
        "total_store_count": store_zone.get("total_store_count"),
        "radius_m": store_zone.get("radius_m"),
    })


async def validate_real_api(start: str, end: str, old_start: str, old_end: str) -> None:
    base_state = {
        "store_location": {
            "district": "마포구",
            "station": "홍대입구역",
            "lat": 37.557192,
            "lng": 126.925381,
        },
    }
    recent_result = await api.fetch_external_data({
        **base_state,
        "date_range": {"start": start, "end": end},
    })
    _summarize_external_data(f"real_api {start}~{end}", recent_result)

    old_result = await api.fetch_external_data({
        **base_state,
        "date_range": {"start": old_start, "end": old_end},
    })
    _summarize_external_data(f"real_api old {old_start}~{old_end}", old_result)


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--real", action="store_true", help="Call configured public APIs")
    parser.add_argument("--start", default="2026-05-01")
    parser.add_argument("--end", default="2026-05-07")
    parser.add_argument("--old-start", default="2000-01-01")
    parser.add_argument("--old-end", default="2000-01-01")
    args = parser.parse_args()

    load_dotenv(PROJECT_ROOT / ".env")
    await validate_without_network()
    if args.real:
        await validate_real_api(args.start, args.end, args.old_start, args.old_end)


if __name__ == "__main__":
    asyncio.run(main())
