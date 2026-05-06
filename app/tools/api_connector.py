"""
외부 공공 데이터를 수집합니다. 실패 시 보간 엔진으로 자동 fallback.
"""
import asyncio
from datetime import date as date_type, datetime, timedelta
import math
from typing import Optional

import httpx

from app.agent.state import AgentState
import os

API_ENDPOINTS = {
    "weather":     "https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getUltraSrtNcst",
    "ecos":        "https://ecos.bok.or.kr/api",
    "subway":      "http://openapi.seoul.go.kr:8088",
    "store_zone":  "http://apis.data.go.kr/B553077/api/open/sdsc2/storeListInRadius",
    "living_idx":  "https://apis.data.go.kr/1360000/LivingWthrIdxServiceV4/getSenTaIdxV4",
}

# 기상청 생활기상지수 API 지역코드 (구 단위 → 10자리 코드)
DISTRICT_AREA_CODE: dict[str, str] = {
    "강남구": "1168000000", "강동구": "1174000000", "강북구": "1130500000",
    "강서구": "1150000000", "관악구": "1162000000", "광진구": "1121500000",
    "구로구": "1153000000", "금천구": "1154500000", "노원구": "1135000000",
    "도봉구": "1132000000", "동대문구": "1123000000", "동작구": "1159000000",
    "마포구": "1144000000", "서대문구": "1141000000", "서초구": "1165000000",
    "성동구": "1120000000", "성북구": "1129000000", "송파구": "1171000000",
    "양천구": "1147000000", "영등포구": "1156000000", "용산구": "1117000000",
    "은평구": "1138000000", "종로구": "1111000000", "중구": "1114000000",
    "중랑구": "1126000000",
}

SENSIBLE_TEMP_REQUEST_CODES: dict[str, str] = {
    "road": "A47",
    "vulnerable_living": "A46",
}

PRECIPITATION_TYPE = {
    "0": "none",
    "1": "rain",
    "2": "rain_snow",
    "3": "snow",
    "5": "raindrop",
    "6": "raindrop_snow",
    "7": "snow_flurry",
}

ECOS_INDICATORS = {
    "consumer_price_index": {
        "stat_code": "901Y009",
        "cycle": "M",
        "item_code1": "0",
        "label": "소비자물가지수",
    },
    "restaurant_price_index": {
        "stat_code": "901Y009",
        "cycle": "M",
        "item_code1": "FD",
        "label": "외식 물가지수",
    },
    "base_rate": {
        "stat_code": "722Y001",
        "cycle": "M",
        "item_code1": "0101000",
        "label": "한국은행 기준금리",
    },
}


def _lat_lng_to_grid(lat: float, lng: float) -> tuple[int, int]:
    """위도/경도를 기상청 동네예보 격자 좌표(nx, ny)로 변환합니다."""
    re = 6371.00877
    grid = 5.0
    slat1 = 30.0
    slat2 = 60.0
    olon = 126.0
    olat = 38.0
    xo = 43
    yo = 136

    degrad = math.pi / 180.0
    re_grid = re / grid
    slat1_rad = slat1 * degrad
    slat2_rad = slat2 * degrad
    olon_rad = olon * degrad
    olat_rad = olat * degrad

    sn = math.tan(math.pi * 0.25 + slat2_rad * 0.5) / math.tan(math.pi * 0.25 + slat1_rad * 0.5)
    sn = math.log(math.cos(slat1_rad) / math.cos(slat2_rad)) / math.log(sn)
    sf = math.tan(math.pi * 0.25 + slat1_rad * 0.5)
    sf = (sf ** sn) * math.cos(slat1_rad) / sn
    ro = math.tan(math.pi * 0.25 + olat_rad * 0.5)
    ro = re_grid * sf / (ro ** sn)

    ra = math.tan(math.pi * 0.25 + lat * degrad * 0.5)
    ra = re_grid * sf / (ra ** sn)
    theta = lng * degrad - olon_rad
    if theta > math.pi:
        theta -= 2.0 * math.pi
    if theta < -math.pi:
        theta += 2.0 * math.pi
    theta *= sn

    nx = int(ra * math.sin(theta) + xo + 0.5)
    ny = int(ro - ra * math.cos(theta) + yo + 0.5)
    return nx, ny


def _to_kma_weather_base(date: str) -> tuple[str, str]:
    """초단기실황 발표일자/시각(base_date, base_time)을 계산합니다."""
    if date:
        try:
            parsed = datetime.fromisoformat(date)
            return parsed.strftime("%Y%m%d"), "1200"
        except ValueError:
            pass

    now_kst = datetime.utcnow().replace(microsecond=0) + timedelta(hours=9)
    if now_kst.minute < 45:
        now_kst -= timedelta(hours=1)
    return now_kst.strftime("%Y%m%d"), now_kst.strftime("%H00")


def _extract_kma_items(payload: dict) -> list[dict]:
    response = payload.get("response", {})
    header = response.get("header", {})
    if header and header.get("resultCode") not in (None, "00"):
        return []

    body = response.get("body", {})
    items = body.get("items", {})
    item = items.get("item") if isinstance(items, dict) else items

    if isinstance(item, list):
        return item
    if isinstance(item, dict):
        return [item]
    return []


def _normalize_weather(items: list[dict], district: str, nx: int, ny: int) -> Optional[dict]:
    if not items:
        return None

    values = {
        item.get("category"): item.get("obsrValue")
        for item in items
        if item.get("category")
    }
    precipitation_type = PRECIPITATION_TYPE.get(str(values.get("PTY", "0")), "unknown")
    condition = "cloudy"
    if precipitation_type in {"rain", "raindrop"}:
        condition = "rainy"
    elif precipitation_type in {"snow", "snow_flurry", "rain_snow", "raindrop_snow"}:
        condition = "snow"
    elif precipitation_type == "none":
        condition = "sunny"

    return {
        "source": "KMA VilageFcstInfoService_2.0",
        "district": district,
        "grid": {"nx": nx, "ny": ny},
        "condition": condition,
        "precipitation_type": precipitation_type,
        "temperature_c": _to_float(values.get("T1H")),
        "rainfall_1h_mm": values.get("RN1"),
        "humidity_percent": _to_float(values.get("REH")),
        "wind_speed_ms": _to_float(values.get("WSD")),
        "wind_direction_deg": _to_float(values.get("VEC")),
        "raw": values,
    }


def _to_float(value: object) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value: object) -> int:
    try:
        return int(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return 0


async def _fetch_weather(district: str, lat: Optional[float], lng: Optional[float], date: str) -> Optional[dict]:
    api_key = os.getenv("KMA_API_KEY", "")
    if not api_key or lat is None or lng is None:
        return None

    try:
        nx, ny = _lat_lng_to_grid(float(lat), float(lng))
        base_date, base_time = _to_kma_weather_base(date)
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                API_ENDPOINTS["weather"],
                params={
                    "serviceKey": api_key,
                    "pageNo": 1,
                    "numOfRows": 1000,
                    "dataType": "JSON",
                    "base_date": base_date,
                    "base_time": base_time,
                    "nx": nx,
                    "ny": ny,
                },
            )
            if resp.status_code != 200:
                return None
            try:
                payload = resp.json()
            except ValueError:
                return None
            return _normalize_weather(_extract_kma_items(payload), district, nx, ny)
    except Exception:
        return None


def _to_ecos_month(date: str) -> str:
    if date:
        try:
            return datetime.fromisoformat(date).strftime("%Y%m")
        except ValueError:
            pass
    return (datetime.utcnow() + timedelta(hours=9)).strftime("%Y%m")


def _shift_month(month: str, offset: int) -> str:
    year = int(month[:4])
    month_num = int(month[4:])
    month_num += offset
    while month_num <= 0:
        year -= 1
        month_num += 12
    while month_num > 12:
        year += 1
        month_num -= 12
    return f"{year}{month_num:02d}"


def _extract_ecos_rows(payload: dict, service_name: str = "StatisticSearch") -> list[dict]:
    service = payload.get(service_name, {})
    if service.get("RESULT", {}).get("CODE") not in (None, "INFO-000"):
        return []

    rows = service.get("row", [])
    if isinstance(rows, list):
        return rows
    if isinstance(rows, dict):
        return [rows]
    return []


def _normalize_ecos_indicator(name: str, config: dict, rows: list[dict]) -> Optional[dict]:
    if not rows:
        return None

    parsed_rows = []
    for row in rows:
        value = _to_float(row.get("DATA_VALUE"))
        if value is None:
            continue
        parsed_rows.append(
            {
                "time": row.get("TIME"),
                "value": value,
                "unit": row.get("UNIT_NAME"),
                "item_name": row.get("ITEM_NAME1"),
            }
        )

    if not parsed_rows:
        return None

    latest = parsed_rows[-1]
    previous = parsed_rows[-2] if len(parsed_rows) >= 2 else None
    change = None
    if previous:
        change = round(latest["value"] - previous["value"], 4)

    return {
        "name": name,
        "label": config["label"],
        "stat_code": config["stat_code"],
        "cycle": config["cycle"],
        "latest": latest,
        "previous": previous,
        "change_from_previous": change,
        "series": parsed_rows,
    }


async def _fetch_ecos_indicator(
    client: httpx.AsyncClient,
    name: str,
    config: dict,
    start_month: str,
    end_month: str,
) -> Optional[dict]:
    api_key = os.getenv("ECOS_API_KEY", "")
    url = (
        f"{API_ENDPOINTS['ecos']}/StatisticSearch/"
        f"{api_key}/json/kr/1/100/"
        f"{config['stat_code']}/{config['cycle']}/{start_month}/{end_month}/{config['item_code1']}"
    )
    resp = await client.get(url)
    if resp.status_code != 200:
        return None

    try:
        payload = resp.json()
    except ValueError:
        return None

    return _normalize_ecos_indicator(name, config, _extract_ecos_rows(payload))


async def _fetch_price_index(date: str) -> Optional[dict]:
    api_key = os.getenv("ECOS_API_KEY", "")
    if not api_key:
        return None

    try:
        end_month = _to_ecos_month(date)
        start_month = _shift_month(end_month, -12)
        async with httpx.AsyncClient(timeout=10) as client:
            results = await asyncio.gather(
                *[
                    _fetch_ecos_indicator(client, name, config, start_month, end_month)
                    for name, config in ECOS_INDICATORS.items()
                ],
                return_exceptions=True,
            )

        indicators = {}
        for name, result in zip(ECOS_INDICATORS.keys(), results):
            if isinstance(result, Exception) or result is None:
                continue
            indicators[name] = result

        if not indicators:
            return None

        return {
            "source": "Bank of Korea ECOS",
            "start_month": start_month,
            "end_month": end_month,
            "indicators": indicators,
        }
    except Exception:
        return None


def _to_living_idx_time(date: str) -> str:
    """기상청 생활기상지수 time 파라미터 형식(YYYYMMDDHH)으로 변환합니다."""
    if not date:
        return datetime.utcnow().strftime("%Y%m%d18")

    try:
        parsed = datetime.fromisoformat(date)
    except ValueError:
        parsed = datetime.utcnow()

    return parsed.strftime("%Y%m%d18")


def _extract_living_idx_item(payload: dict) -> Optional[dict]:
    response = payload.get("response", {})
    header = response.get("header", {})
    if header and header.get("resultCode") not in (None, "00"):
        return None

    body = response.get("body", {})
    items = body.get("items", {})
    item = items.get("item") if isinstance(items, dict) else items

    if isinstance(item, list):
        return item[0] if item else None
    if isinstance(item, dict):
        return item
    return None


async def _fetch_living_idx_by_code(
    client: httpx.AsyncClient,
    area_no: str,
    time_str: str,
    request_code: str,
) -> Optional[dict]:
    resp = await client.get(
        API_ENDPOINTS["living_idx"],
        params={
            "serviceKey": os.getenv("KMA_API_KEY", ""),
            "pageNo": 1,
            "numOfRows": 10,
            "dataType": "JSON",
            "areaNo": area_no,
            "time": time_str,
            "requestCode": request_code,
        },
    )
    if resp.status_code != 200:
        return None

    try:
        payload = resp.json()
    except ValueError:
        return None

    return _extract_living_idx_item(payload)


async def _fetch_living_idx(district: str, date: str) -> Optional[dict]:
    area_no = DISTRICT_AREA_CODE.get(district)
    if not area_no:
        return None

    api_key = os.getenv("KMA_API_KEY", "")
    if not api_key:
        return None

    try:
        time_str = _to_living_idx_time(date)
        async with httpx.AsyncClient(timeout=10) as client:
            results = await asyncio.gather(
                *[
                    _fetch_living_idx_by_code(client, area_no, time_str, code)
                    for code in SENSIBLE_TEMP_REQUEST_CODES.values()
                ],
                return_exceptions=True,
            )

        indexes = {}
        for name, result in zip(SENSIBLE_TEMP_REQUEST_CODES.keys(), results):
            if isinstance(result, Exception) or result is None:
                continue
            indexes[name] = result

        if not indexes:
            return None

        return {
            "source": "KMA LivingWthrIdxServiceV4",
            "index_type": "sensible_temperature",
            "district": district,
            "area_no": area_no,
            "time": time_str,
            "indexes": indexes,
        }
    except Exception:
        return None


def _parse_iso_date(value: str) -> Optional[date_type]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).date()
    except ValueError:
        return None


def _iter_dates(start: date_type, end: date_type) -> list[date_type]:
    days = (end - start).days
    if days < 0:
        return []
    return [start + timedelta(days=offset) for offset in range(days + 1)]


def _week_bounds(day: date_type) -> tuple[date_type, date_type]:
    start = day - timedelta(days=day.weekday())
    return start, start + timedelta(days=6)


def _month_bounds(day: date_type) -> tuple[date_type, date_type]:
    start = day.replace(day=1)
    next_month = start.replace(year=start.year + 1, month=1) if start.month == 12 else start.replace(month=start.month + 1)
    return start, next_month - timedelta(days=1)


def _to_seoul_openapi_date(date: str) -> str:
    """서울 열린데이터 일 단위 API 날짜 형식(YYYYMMDD)으로 변환합니다."""
    if date:
        try:
            return datetime.fromisoformat(date).strftime("%Y%m%d")
        except ValueError:
            pass

    # 지하철 승하차 데이터는 보통 며칠 늦게 적재되므로 기본값은 3일 전입니다.
    return (datetime.utcnow() + timedelta(hours=9) - timedelta(days=3)).strftime("%Y%m%d")


def _normalize_station_name(station: str) -> str:
    return station.strip().replace("역", "").replace(" ", "")


def _extract_subway_rows(payload: dict) -> list[dict]:
    result = payload.get("CardSubwayStatsNew", {})
    rows = result.get("row", [])
    if isinstance(rows, list):
        return rows
    if isinstance(rows, dict):
        return [rows]
    return []


def _normalize_subway_data(payload: dict, station: str, use_date: str) -> Optional[dict]:
    rows = _extract_subway_rows(payload)
    if not rows:
        return None

    target_station = _normalize_station_name(station)
    matched_rows = [
        row for row in rows
        if _normalize_station_name(str(row.get("SUB_STA_NM", ""))) == target_station
    ]
    if not matched_rows:
        return None

    ride_total = sum(_to_int(row.get("RIDE_PASGR_NUM")) for row in matched_rows)
    alight_total = sum(_to_int(row.get("ALIGHT_PASGR_NUM")) for row in matched_rows)

    return {
        "source": "Seoul Open Data CardSubwayStatsNew",
        "station": station,
        "use_date": use_date,
        "date_scope": "day",
        "ride_passenger_count": ride_total,
        "alight_passenger_count": alight_total,
        "total_passenger_count": ride_total + alight_total,
        "lines": [
            {
                "line": row.get("LINE_NUM"),
                "station": row.get("SUB_STA_NM"),
                "ride_passenger_count": _to_int(row.get("RIDE_PASGR_NUM")),
                "alight_passenger_count": _to_int(row.get("ALIGHT_PASGR_NUM")),
                "work_date": row.get("WORK_DT"),
            }
            for row in matched_rows
        ],
    }


async def _fetch_subway_for_date(client: httpx.AsyncClient, api_key: str, station: str, target_date: date_type) -> Optional[dict]:
    use_date = target_date.strftime("%Y%m%d")
    url = f"{API_ENDPOINTS['subway']}/{api_key}/json/CardSubwayStatsNew/1/1000/{use_date}"
    resp = await client.get(url)
    if resp.status_code != 200:
        return None
    try:
        payload = resp.json()
    except ValueError:
        return None
    return _normalize_subway_data(payload, station, use_date)


def _combine_subway_results(results: list[dict], station: str, scope: str) -> Optional[dict]:
    valid_results = [result for result in results if result]
    if not valid_results:
        return None

    ride_total = sum(result["ride_passenger_count"] for result in valid_results)
    alight_total = sum(result["alight_passenger_count"] for result in valid_results)
    count = len(valid_results)

    return {
        "source": "Seoul Open Data CardSubwayStatsNew",
        "station": station,
        "date_scope": scope,
        "start_date": valid_results[0]["use_date"],
        "end_date": valid_results[-1]["use_date"],
        "days_collected": count,
        "ride_passenger_count": ride_total,
        "alight_passenger_count": alight_total,
        "total_passenger_count": ride_total + alight_total,
        "avg_daily_total_passenger_count": round((ride_total + alight_total) / count, 2),
        "daily": valid_results,
    }


async def _fetch_subway(station: str, start_date: str, end_date: str = "") -> Optional[dict]:
    api_key = os.getenv("SEOUL_API_KEY", "")
    if not api_key or not station:
        return None

    start = _parse_iso_date(start_date)
    end = _parse_iso_date(end_date) or start
    if not start:
        start = (datetime.utcnow() + timedelta(hours=9) - timedelta(days=3)).date()
        end = start

    exact_dates = _iter_dates(start, end) if start and end else []
    query_windows: list[tuple[str, list[date_type]]] = []
    if exact_dates and len(exact_dates) <= 7:
        query_windows.append(("exact", exact_dates))

    week_start, week_end = _week_bounds(start)
    query_windows.append(("week", _iter_dates(week_start, week_end)))

    month_start, month_end = _month_bounds(start)
    query_windows.append(("month", _iter_dates(month_start, month_end)))

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            for scope, dates in query_windows:
                results = await asyncio.gather(
                    *[_fetch_subway_for_date(client, api_key, station, day) for day in dates],
                    return_exceptions=True,
                )
                normalized = [
                    result for result in results
                    if not isinstance(result, Exception) and result is not None
                ]
                combined = _combine_subway_results(normalized, station, scope)
                if combined:
                    return combined
    except Exception:
        return None

    return None


def _extract_store_zone_items(payload: dict) -> list[dict]:
    header = payload.get("header", {})
    if header and str(header.get("resultCode")) not in ("00", "0", "None"):
        return []

    body = payload.get("body", {})
    items = body.get("items", [])
    if isinstance(items, list):
        return items
    if isinstance(items, dict):
        item = items.get("item", items)
        if isinstance(item, list):
            return item
        if isinstance(item, dict):
            return [item]
    return []


def _summarize_store_zone(items: list[dict], lat: float, lng: float, radius: int) -> Optional[dict]:
    if not items:
        return None

    large_categories: dict[str, int] = {}
    middle_categories: dict[str, int] = {}
    small_categories: dict[str, int] = {}

    for item in items:
        large = item.get("indsLclsNm") or "미분류"
        middle = item.get("indsMclsNm") or "미분류"
        small = item.get("indsSclsNm") or "미분류"
        large_categories[large] = large_categories.get(large, 0) + 1
        middle_categories[middle] = middle_categories.get(middle, 0) + 1
        small_categories[small] = small_categories.get(small, 0) + 1

    area_km2 = math.pi * (radius / 1000) ** 2
    density = round(len(items) / area_km2, 2) if area_km2 else None

    def top_counts(counts: dict[str, int], limit: int = 10) -> list[dict]:
        return [
            {"name": name, "count": count}
            for name, count in sorted(counts.items(), key=lambda row: row[1], reverse=True)[:limit]
        ]

    return {
        "source": "SEMAS Store Zone API",
        "center": {"lat": lat, "lng": lng},
        "radius_m": radius,
        "total_store_count": len(items),
        "store_density_per_km2": density,
        "top_large_categories": top_counts(large_categories),
        "top_middle_categories": top_counts(middle_categories),
        "top_small_categories": top_counts(small_categories),
        "sample_stores": [
            {
                "name": item.get("bizesNm"),
                "branch": item.get("brchNm"),
                "large_category": item.get("indsLclsNm"),
                "middle_category": item.get("indsMclsNm"),
                "small_category": item.get("indsSclsNm"),
                "road_address": item.get("rdnmAdr"),
                "lon": _to_float(item.get("lon")),
                "lat": _to_float(item.get("lat")),
            }
            for item in items[:20]
        ],
    }


async def _fetch_store_zone(lat: Optional[float], lng: Optional[float], radius: int = 500) -> Optional[dict]:
    api_key = os.getenv("STORE_ZONE_API_KEY", "")
    if not api_key or lat is None or lng is None:
        return None

    try:
        lat_value = float(lat)
        lng_value = float(lng)
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                API_ENDPOINTS["store_zone"],
                params={
                    "serviceKey": api_key,
                    "radius": radius,
                    "cx": lng_value,
                    "cy": lat_value,
                    "numOfRows": 1000,
                    "pageNo": 1,
                    "type": "json",
                },
            )
            if resp.status_code != 200:
                return None
            try:
                payload = resp.json()
            except ValueError:
                return None
            return _summarize_store_zone(
                _extract_store_zone_items(payload),
                lat=lat_value,
                lng=lng_value,
                radius=radius,
            )
    except Exception:
        return None


async def fetch_external_data(state: AgentState) -> AgentState:
    date_range = state.get("date_range", {})
    start_date = date_range.get("start", "") if date_range else ""
    end_date = date_range.get("end", "") if date_range else ""
    loc = state.get("store_location") or {}
    district = loc.get("district", "")
    station = loc.get("station", "")
    lat = loc.get("lat")
    lng = loc.get("lng")

    weather, price, subway, living_idx, store_zone = await asyncio.gather(
        _fetch_weather(district, lat, lng, start_date),
        _fetch_price_index(start_date),
        _fetch_subway(station, start_date, end_date),
        _fetch_living_idx(district, start_date),
        _fetch_store_zone(lat, lng),
    )

    missing_fields = []
    if weather is None:
        missing_fields.append("weather")
    if subway is None:
        missing_fields.append("population_flow")
    if price is None:
        missing_fields.append("price_index")
    if living_idx is None:
        missing_fields.append("living_idx")
    if store_zone is None:
        missing_fields.append("store_zone")

    external_data = {
        "weather": weather,
        "price_index": price,
        "subway": subway,
        "living_idx": living_idx,
        "store_zone": store_zone,
        "missing_fields": missing_fields,
    }

    return {
        "external_data": external_data,
        "tool_calls": [{"tool": "api_connector", "missing": missing_fields}],
    }
