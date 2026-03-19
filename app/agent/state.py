from typing import TypedDict, List, Optional, Annotated
from operator import add


class AgentState(TypedDict):
    # 입력
    user_query: str
    store_id: str
    uploaded_file_path: Optional[str]
    mode: str                                               # "quick" | "deep"
    date_range: Optional[dict]                              # {"start": ..., "end": ...}

    # 계획 단계
    hypotheses: List[str]
    analysis_plan: List[str]

    # 실행 단계
    tool_calls: Annotated[List[dict], add]
    internal_data: Optional[dict]
    external_data: Optional[dict]
    estimated_data: Optional[dict]
    rag_context: Optional[str]

    # 분석 단계
    correlation_results: Optional[dict]
    statistical_summary: Optional[str]

    # 출력 단계
    final_report_json: Optional[dict]
    chart_data: Optional[dict]
    retry_count: int
    is_sufficient: bool
