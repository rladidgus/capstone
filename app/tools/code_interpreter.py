"""
업로드된 CSV/XLSX를 분석하기 위해 LLM이 생성한 Pandas 코드를 실행합니다.
"""
import io
import traceback
from typing import Any

import pandas as pd
from RestrictedPython import compile_restricted, safe_globals

from app.agent.state import AgentState
from app.services.llm_service import LLMService

llm = LLMService()

CODE_GEN_PROMPT = """
다음 CSV 데이터를 Pandas로 분석하는 Python 코드를 작성하세요.
분석 요청: {request}
컬럼 정보: {columns}

규칙:
- pandas를 pd로 import하여 사용
- 결과를 result 변수에 dict 형태로 저장
- print 사용 금지
- 외부 라이브러리 import 금지 (pandas, numpy 제외)

Python 코드만 출력하세요 (마크다운 코드블록 없이):
"""


def _run_safe(code: str, df: pd.DataFrame) -> dict[str, Any]:
    restricted_globals = {
        **safe_globals,
        "pd": pd,
        "df": df,
        "__builtins__": {"len": len, "range": range, "list": list, "dict": dict,
                         "str": str, "int": int, "float": float, "round": round},
    }
    local_vars: dict = {}
    byte_code = compile_restricted(code, "<string>", "exec")
    exec(byte_code, restricted_globals, local_vars)
    return local_vars.get("result", {})


async def run_code_interpreter(state: AgentState) -> AgentState:
    file_path = state.get("uploaded_file_path")
    if not file_path:
        return state

    df = pd.read_csv(file_path) if file_path.endswith(".csv") else pd.read_excel(file_path)
    columns_info = df.dtypes.to_dict()

    prompt = CODE_GEN_PROMPT.format(
        request=state["user_query"],
        columns={k: str(v) for k, v in columns_info.items()},
    )
    generated_code = await llm.generate_text(prompt)

    try:
        result = _run_safe(generated_code, df)
    except Exception:
        result = {"error": traceback.format_exc(), "generated_code": generated_code}

    return {
        **state,
        "internal_data": result,
        "tool_calls": [{"tool": "code_interpreter", "status": "done"}],
    }
