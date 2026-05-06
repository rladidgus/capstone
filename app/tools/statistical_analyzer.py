"""
수집·추정된 데이터 간의 통계적 관계를 검증합니다.
"""
from typing import Optional

import numpy as np
from scipy import stats

from app.agent.state import AgentState


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

    sales_series = internal.get("time_series", [])
    correlation_results: dict = {}
    summary_lines: list[str] = []

    # 유동인구 vs 매출 상관분석
    # subway 데이터가 실제 시계열 리스트일 때만 상관분석 수행
    subway_data = external.get("subway")
    population_series = subway_data if isinstance(subway_data, list) else []

    if sales_series and len(population_series) == len(sales_series):
        pop_corr = analyze_correlation(sales_series, population_series)
        correlation_results["population_vs_sales"] = pop_corr
        summary_lines.append(
            f"유동인구-매출 상관: r={pop_corr.get('r_value')}, p={pop_corr.get('p_value')}"
        )
    else:
        # 단일 추정값만 있는 경우 — 상관분석 불가, 참고용 수치만 기록
        estimated_pop = estimated.get("population_flow", {})
        if isinstance(estimated_pop, dict) and "estimated_value" in estimated_pop:
            correlation_results["population_vs_sales"] = {
                "skipped": True,
                "reason": "실시간 지하철 데이터 미수집 — 단일 추정값으로 상관분석 불가",
                "estimated_population": estimated_pop["estimated_value"],
            }
            summary_lines.append(
                f"유동인구 추정치: {estimated_pop['estimated_value']}명 (상관분석 생략 — 단일 추정값)"
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
