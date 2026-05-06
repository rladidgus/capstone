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
  "action_items": ["즉시 실행방안1", "즉시 실행방안2", "즉시 실행방안3"]
}}
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
  "action_items": ["실행방안1", "실행방안2", "실행방안3", "실행방안4", "실행방안5"]
}}
"""


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
    return {
        "final_report_json": report_json,
    }
