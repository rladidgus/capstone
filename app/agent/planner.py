from app.agent.state import AgentState
from app.services.llm_service import LLMService

llm = LLMService()

PLANNER_PROMPT_QUICK = """
당신은 소상공인 경영 분석 전문가입니다.
사용자의 질문에 대해 핵심 가설 1~2개와 간단한 분석 계획을 수립하세요.
빠른 브리핑이 목적이므로 가장 중요한 요인에만 집중하세요.

사용자 질문: {query}
분석 기간: {date_range}

다음 JSON 형식으로 응답하세요:
{{
  "hypotheses": ["핵심 가설1", "핵심 가설2"],
  "analysis_plan": ["단계1", "단계2"]
}}
"""

PLANNER_PROMPT_DEEP = """
당신은 소상공인 경영 분석 전문가입니다.
사용자의 질문을 다각도로 분석하여 검증할 가설 3개 이상과 단계별 분석 계획을 수립하세요.
내부 매출 데이터, 외부 경제 지표, 유동인구, 날씨 등 가능한 모든 요인을 고려하세요.

사용자 질문: {query}
분석 기간: {date_range}

다음 JSON 형식으로 응답하세요:
{{
  "hypotheses": ["가설1", "가설2", "가설3", "가설4"],
  "analysis_plan": ["단계1", "단계2", "단계3", "단계4", "단계5"]
}}
"""


def _build_quick_plan(state: AgentState) -> dict:
    date_range = state.get("date_range") or {}
    date_label = "업로드된 매출 기간"
    if isinstance(date_range, dict) and date_range.get("start") and date_range.get("end"):
        date_label = f"{date_range['start']}~{date_range['end']}"

    return {
        "hypotheses": [
            f"{date_label}의 매출 변화는 시간대/요일별 수요 차이와 관련이 있을 수 있다.",
            "외부 유동인구, 날씨, 물가 지표가 매출 변동을 보조적으로 설명할 수 있다.",
        ],
        "analysis_plan": [
            "업로드 매출 데이터의 기간, 총매출, 시간대별 패턴을 요약한다.",
            "외부 API와 통계 분석 결과를 결합해 핵심 원인과 실행 방안을 도출한다.",
        ],
    }


async def run_planner(state: AgentState) -> AgentState:
    mode = state.get("mode", "deep")
    if mode == "quick":
        return _build_quick_plan(state)

    prompt_template = PLANNER_PROMPT_QUICK if mode == "quick" else PLANNER_PROMPT_DEEP
    prompt = prompt_template.format(
        query=state["user_query"],
        date_range=state.get("date_range", "전체 기간"),
    )
    result = await llm.generate_json(prompt)
    return {
        "hypotheses": result.get("hypotheses", []),
        "analysis_plan": result.get("analysis_plan", []),
    }
