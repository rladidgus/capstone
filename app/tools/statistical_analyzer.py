"""
수집·추정된 데이터 간의 통계적 관계를 검증합니다.
"""
from typing import Optional

import numpy as np
from scipy import stats

from app.agent.state import AgentState


def _to_float(value: object) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _extract_numeric_series(series: object, value_keys: tuple[str, ...] = ("amount", "sales", "value")) -> list[float]:
    """숫자 리스트 또는 dict 리스트에서 분석 가능한 숫자 시계열만 추출합니다."""
    if not isinstance(series, list):
        return []

    values: list[float] = []
    for item in series:
        if isinstance(item, dict):
            value = None
            for key in value_keys:
                if key in item:
                    value = item.get(key)
                    break
        else:
            value = item

        parsed = _to_float(value)
        if parsed is not None:
            values.append(parsed)

    return values


def analyze_correlation(sales_data: list[float], factor_data: list[float]) -> dict:
    """피어슨 상관계수 및 p-value 계산"""
    if len(sales_data) < 3 or len(factor_data) < 3:
        return {"error": "데이터 포인트 부족 (최소 3개 필요)"}

    r, p = stats.pearsonr(sales_data, factor_data)
    abs_r = abs(r)

    if abs_r >= 0.7:
        strength = "강한"
    elif abs_r >= 0.4:
        strength = "중간"
    else:
        strength = "약한"

    direction = "양의" if r > 0 else "음의"
    interpretation = f"{strength} {direction} 상관관계"

    return {
        "r_value": round(float(r), 4),
        "p_value": round(float(p), 4),
        "is_significant": bool(p < 0.05),
        "interpretation": interpretation,
    }


def detect_trend_break(time_series: list[float]) -> dict:
    """매출 추세 급변 시점 탐지 (단순 Chow Test 근사)"""
    n = len(time_series)
    if n < 6:
        return {"error": "데이터 포인트 부족"}

    mid = n // 2
    before = time_series[:mid]
    after = time_series[mid:]

    before_avg = float(np.mean(before))
    after_avg = float(np.mean(after))
    change_rate = ((after_avg - before_avg) / before_avg * 100) if before_avg != 0 else 0.0

    return {
        "before_avg": round(before_avg, 2),
        "after_avg": round(after_avg, 2),
        "change_rate": round(change_rate, 2),
        "break_index": mid,
    }


async def run_statistical_analysis(state: AgentState) -> AgentState:
    internal = state.get("internal_data") or {}
    external = state.get("external_data") or {}
    estimated = state.get("estimated_data") or {}

    sales_series = _extract_numeric_series(internal.get("time_series", []))
    correlation_results: dict = {}
    summary_lines: list[str] = []

    # 유동인구 vs 매출 상관분석
    # subway 데이터가 실제 시계열 리스트일 때만 상관분석 수행
    subway_data = external.get("subway")
    population_series = _extract_numeric_series(
        subway_data,
        value_keys=("total_passenger_count", "population", "value", "amount"),
    )

    if sales_series and len(population_series) == len(sales_series):
        pop_corr = analyze_correlation(sales_series, population_series)
        correlation_results["population_vs_sales"] = pop_corr
        summary_lines.append(
            f"유동인구-매출 상관: r={pop_corr.get('r_value')}, p={pop_corr.get('p_value')}"
        )
    else:
        # 보간 활동 지수만 있는 경우 — 실제 유동인구 수가 아니므로 상관분석 불가, 참고용으로만 기록
        estimated_pop = estimated.get("population_flow", {})
        if isinstance(estimated_pop, dict) and "estimated_value" in estimated_pop:
            correlation_results["population_vs_sales"] = {
                "skipped": True,
                "reason": "실시간 지하철 데이터 미수집 — 매출 기반 활동 지수는 실제 유동인구 수가 아니므로 상관분석 불가",
                "replacement_type": estimated_pop.get("replacement_type", "business_activity_index"),
                "is_actual_population": estimated_pop.get("is_actual_population", False),
                "estimated_activity_index": estimated_pop["estimated_value"],
                "unit": estimated_pop.get("unit", "activity_index"),
                "period_start": estimated_pop.get("period_start"),
                "period_end": estimated_pop.get("period_end"),
            }
            summary_lines.append(
                f"유동인구 데이터 없음 — 매출 기반 활동 지수 평균 {estimated_pop['estimated_value']} "
                f"({estimated_pop.get('period_start')}~{estimated_pop.get('period_end')}, 실제 인구 수 아님)"
            )

    # 추세 분석
    if len(sales_series) >= 6:
        trend = detect_trend_break(sales_series)
        correlation_results["trend_break"] = trend
        summary_lines.append(
            f"매출 추세 변화율: {trend.get('change_rate')}%"
        )

    return {
        "correlation_results": correlation_results,
        "statistical_summary": " | ".join(summary_lines),
        "tool_calls": [{"tool": "statistical_analyzer", "done": True}],
    }
