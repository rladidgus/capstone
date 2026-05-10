from app.agent.state import AgentState
from app.services.llm_service import LLMService

llm = LLMService()

REPORTER_PROMPT_QUICK = """
당신은 소상공인 경영 분석 전문가입니다.
아래 분석 결과를 바탕으로 핵심만 담은 간결한 브리핑을 작성하세요.
요약 2문장, 주요 원인 1~2개, 즉시 실행 가능한 개선안 2~3개에만 집중하세요.

사용자 질문: {query}
내부 데이터: {internal_data}
외부 데이터: {external_data}
통계 요약: {statistical_summary}
경영 메모 맥락: {rag_context}

다음 JSON 형식으로 응답하세요:
{{
  "summary": "핵심 요약 (2문장 이내)",
  "analysis_details": [
    {{
      "factor": "주요 요인",
      "impact": "긍정적|부정적|중립",
      "description": "한 줄 설명"
    }}
  ],
  "action_items": ["즉시 실행방안1", "즉시 실행방안2", "즉시 실행방안3"],
  "chart_data": {{
    "type": "line|bar|multi_line",
    "categories": ["X축 레이블"],
    "series": [
      {{"name": "시리즈명", "data": [1000, 2000]}}
    ]
  }}
}}

차트 데이터가 불확실하면 내부 데이터의 time_series를 사용해 매출 추이 line 차트를 만드세요.
"""

REPORTER_PROMPT_DEEP = """
당신은 20년 차 수석 경영 컨설턴트입니다.
아래 분석 결과를 바탕으로 소상공인을 위한 심층 경영 리포트를 작성하세요.

사용자 질문: {query}
가설: {hypotheses}
내부 데이터: {internal_data}
외부 데이터: {external_data}
보간 추정치: {estimated_data}
상관분석: {correlations}
통계 요약: {statistical_summary}
경영 메모 맥락: {rag_context}

각 요인별로 ① 현상 파악 ② 원리 추론 ③ 경제적 영향을 서술하고,
해결 방안을 5가지 이상 구체적으로 제시하세요.

다음 JSON 형식으로 응답하세요:
{{
  "summary": "전체 요약 (2~3문장)",
  "analysis_details": [
    {{
      "factor": "요인명",
      "impact": "긍정적|부정적|중립",
      "description": "상세 설명 (현상·원리·경제적 영향 포함)"
    }}
  ],
  "action_items": ["실행방안1", "실행방안2", "실행방안3", "실행방안4", "실행방안5"],
  "chart_data": {{
    "type": "line|bar|multi_line",
    "categories": ["X축 레이블"],
    "series": [
      {{"name": "시리즈명", "data": [1000, 2000]}}
    ]
  }}
}}

차트 데이터는 분석 내용을 시각화할 수 있는 형태로 생성하세요.
내부 데이터에 time_series가 있으면 매출 추이를 반드시 포함하고,
외부 데이터나 보간 데이터가 숫자 시계열이 아닐 경우 실제 인구 수처럼 꾸며내지 마세요.
"""


def _to_float(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _extract_time_series_chart(internal_data: dict) -> dict | None:
    time_series = internal_data.get("time_series")
    if not isinstance(time_series, list) or not time_series:
        return None

    categories: list[str] = []
    values: list[float] = []

    for index, item in enumerate(time_series):
        if isinstance(item, dict):
            label = item.get("date") or item.get("label") or item.get("period") or str(index + 1)
            value = item.get("amount") or item.get("sales") or item.get("value")
        else:
            label = str(index + 1)
            value = item

        numeric_value = _to_float(value)
        if numeric_value is None:
            continue
        categories.append(str(label))
        values.append(numeric_value)

    if not values:
        return None

    return {
        "type": "line",
        "categories": categories,
        "series": [{"name": "매출", "data": values}],
    }


def _extract_activity_index_chart(estimated_data: dict) -> dict | None:
    activity = estimated_data.get("business_activity_index") or estimated_data.get("population_flow")
    if not isinstance(activity, dict):
        return None

    daily = activity.get("daily")
    if not isinstance(daily, list) or not daily:
        value = _to_float(activity.get("estimated_value"))
        if value is None:
            return None
        return {
            "type": "bar",
            "categories": ["활동 지수"],
            "series": [{"name": "매출 기반 활동 지수", "data": [value]}],
        }

    categories: list[str] = []
    values: list[float] = []
    for index, item in enumerate(daily):
        if not isinstance(item, dict):
            continue
        value = _to_float(item.get("estimated_value"))
        if value is None:
            continue
        categories.append(str(item.get("date") or index + 1))
        values.append(value)

    if not values:
        return None

    return {
        "type": "line",
        "categories": categories,
        "series": [{"name": "매출 기반 활동 지수", "data": values}],
    }


def _is_valid_chart_data(chart_data: object) -> bool:
    if not isinstance(chart_data, dict):
        return False
    categories = chart_data.get("categories")
    series = chart_data.get("series")
    if not isinstance(categories, list) or not categories:
        return False
    if not isinstance(series, list) or not series:
        return False
    for item in series:
        if not isinstance(item, dict):
            return False
        if not isinstance(item.get("name"), str):
            return False
        data = item.get("data")
        if not isinstance(data, list) or not data:
            return False
        if any(_to_float(value) is None for value in data):
            return False
    return True


def _build_chart_data(state: AgentState, report_json: dict) -> dict | None:
    llm_chart = report_json.get("chart_data") if isinstance(report_json, dict) else None
    if _is_valid_chart_data(llm_chart):
        return llm_chart

    internal_chart = _extract_time_series_chart(state.get("internal_data") or {})
    if internal_chart:
        return internal_chart

    activity_chart = _extract_activity_index_chart(state.get("estimated_data") or {})
    if activity_chart:
        return activity_chart

    return None


def _format_money(value: object) -> str:
    numeric = _to_float(value)
    if numeric is None:
        return "확인된 매출"
    return f"{numeric:,.0f}원"


def _top_menu_label(internal_data: dict) -> str:
    top_menus = internal_data.get("top_menus")
    if isinstance(top_menus, list) and top_menus:
        first = top_menus[0]
        if isinstance(first, dict) and first.get("menu"):
            return str(first["menu"])
    return "상위 판매 메뉴"


def _build_fallback_report(state: AgentState) -> dict:
    internal = state.get("internal_data") or {}
    external = state.get("external_data") or {}
    statistical_summary = state.get("statistical_summary") or ""
    rag_context = str(state.get("rag_context") or "").strip()
    mode = state.get("mode", "quick")

    total_amount = _format_money(internal.get("total_amount"))
    avg_daily = _format_money(internal.get("avg_daily_amount"))
    peak_hour = internal.get("peak_hour")
    peak_hour_text = f"{peak_hour}시" if peak_hour is not None else "주요 영업 시간대"
    top_menu = _top_menu_label(internal)

    missing_fields = external.get("missing_fields") if isinstance(external, dict) else []
    missing_text = ""
    if isinstance(missing_fields, list) and missing_fields:
        missing_text = f" 다만 {', '.join(map(str, missing_fields))} 데이터는 일부 제한되어 보조 해석이 필요합니다."

    summary = (
        f"업로드된 매출 데이터 기준 총매출은 {total_amount}, 일평균 매출은 {avg_daily}입니다. "
        f"{peak_hour_text}와 {top_menu}를 중심으로 매출 패턴을 우선 점검하는 것이 좋습니다.{missing_text}"
    )

    details = [
        {
            "factor": "내부 매출 패턴",
            "impact": "중립",
            "description": (
                f"기간 내 매출은 총 {total_amount}이며, 일평균은 {avg_daily}입니다. "
                f"{mode} mode에서는 검증된 계산 로직으로 일별/시간대별 매출과 상위 메뉴를 요약했습니다."
            ),
        },
        {
            "factor": "시간대와 메뉴 구성",
            "impact": "중립",
            "description": (
                f"매출이 집중되는 시간대는 {peak_hour_text}로 확인되며, "
                f"{top_menu}를 중심으로 피크 시간 운영과 재고 준비를 조정할 수 있습니다."
            ),
        },
    ]

    if statistical_summary:
        stat_text = str(statistical_summary).strip()
        if len(stat_text) < 40:
            stat_text = (
                f"{stat_text}. 이 값은 업로드된 매출 데이터에서 계산된 보조 지표이며, "
                "기간 내 매출 흐름을 판단할 때 내부 매출 패턴과 함께 참고해야 합니다."
            )
        details.append({
            "factor": "통계 분석 결과",
            "impact": "중립",
            "description": stat_text[:400],
        })

    if rag_context and "관련 경영 메모 없음" not in rag_context:
        details.append({
            "factor": "경영 메모",
            "impact": "중립",
            "description": (
                f"관련 메모에서 확인된 운영 힌트는 다음과 같습니다: {rag_context[:300]}. "
                "이 내용은 정량 매출 분석을 보완하는 현장 맥락으로 참고할 수 있습니다."
            ),
        })

    return {
        "summary": summary,
        "analysis_details": details,
        "action_items": [
            f"{peak_hour_text} 전후 인력 배치와 조리/준비 수량을 우선 조정하세요.",
            f"{top_menu}와 함께 구매되는 메뉴를 묶어 세트 또는 추천 메뉴로 노출하세요.",
            "일별 매출이 낮은 날짜를 기준으로 할인, 쿠폰, 재방문 메시지 발송 효과를 비교하세요.",
        ],
    }


def _has_report_content(report_json: object) -> bool:
    if not isinstance(report_json, dict):
        return False
    if report_json.get("error"):
        return False

    summary = report_json.get("summary")
    details = report_json.get("analysis_details")
    actions = report_json.get("action_items")
    return (
        isinstance(summary, str)
        and len(summary.strip()) >= 20
        and isinstance(details, list)
        and len(details) > 0
        and isinstance(actions, list)
        and len(actions) >= 2
    )


def _strip_chart_from_report(report_json: dict) -> dict:
    if isinstance(report_json, dict):
        report_json.pop("chart_data", None)
    return report_json


async def run_reporter(state: AgentState) -> AgentState:
    mode = state.get("mode", "deep")

    if mode == "quick":
        prompt = REPORTER_PROMPT_QUICK.format(
            query=state["user_query"],
            internal_data=state.get("internal_data", {}),
            external_data=state.get("external_data", {}),
            statistical_summary=state.get("statistical_summary", ""),
            rag_context=state.get("rag_context", ""),
        )
        max_tokens = 1024
    else:
        prompt = REPORTER_PROMPT_DEEP.format(
            query=state["user_query"],
            hypotheses=state.get("hypotheses", []),
            internal_data=state.get("internal_data", {}),
            external_data=state.get("external_data", {}),
            estimated_data=state.get("estimated_data", {}),
            correlations=state.get("correlation_results", {}),
            statistical_summary=state.get("statistical_summary", ""),
            rag_context=state.get("rag_context", ""),
        )
        max_tokens = 4096

    report_json = await llm.generate_json(prompt, max_tokens=max_tokens)
    if not _has_report_content(report_json):
        report_json = _build_fallback_report(state)

    chart_data = _build_chart_data(state, report_json)
    report_json = _strip_chart_from_report(report_json)

    return {
        "final_report_json": report_json,
        "chart_data": chart_data,
    }
