from app.agent.state import AgentState
from app.services.llm_service import LLMService

llm = LLMService()

PLANNER_PROMPT = """
당신은 소상공인 경영 분석 전문가입니다.
사용자의 질문을 분석하여 검증할 가설 목록과 분석 계획을 수립하세요.

사용자 질문: {query}
분석 기간: {date_range}

다음 JSON 형식으로 응답하세요:
{{
  "hypotheses": ["가설1", "가설2", "가설3"],
  "analysis_plan": ["단계1", "단계2", "단계3"]
}}
"""


async def run_planner(state: AgentState) -> AgentState:
    prompt = PLANNER_PROMPT.format(
        query=state["user_query"],
        date_range=state.get("date_range", "전체 기간"),
    )
    result = await llm.generate_json(prompt)
    return {
        "hypotheses": result.get("hypotheses", []),
        "analysis_plan": result.get("analysis_plan", []),
    }
