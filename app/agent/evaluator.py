from app.agent.state import AgentState
from app.services.llm_service import LLMService

llm = LLMService()

EVALUATOR_PROMPT = """
다음 분석 결과가 사용자 질문에 충분히 답변하는지 평가하세요.

사용자 질문: {query}
수립된 가설: {hypotheses}
상관분석 결과: {correlations}
통계 요약: {statistical_summary}
RAG 컨텍스트: {rag_context}

판단 기준:
- 최소 1개 이상의 가설이 통계적으로 검증되었는가 (p < 0.05)
- 상관계수 |r| > 0.5 인 요인이 존재하는가
- 실행 가능한 개선안을 도출할 수 있는가

다음 JSON 형식으로 응답하세요:
{{"is_sufficient": true/false, "reason": "판단 이유"}}
"""


async def run_evaluator(state: AgentState) -> AgentState:
    prompt = EVALUATOR_PROMPT.format(
        query=state["user_query"],
        hypotheses=state.get("hypotheses", []),
        correlations=state.get("correlation_results", {}),
        statistical_summary=state.get("statistical_summary", ""),
        rag_context=state.get("rag_context", ""),
    )
    result = await llm.generate_json(prompt)
    return {
        **state,
        "is_sufficient": result.get("is_sufficient", False),
        "retry_count": state.get("retry_count", 0) + 1,
    }
