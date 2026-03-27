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
    def _write_guard(obj):
        return obj  # 안전장치를 통과시키는 더미 래퍼

    restricted_globals = {
        **safe_globals,
        "pd": pd,
        "df": df,
        "__builtins__": {
            "len": len, "range": range, "list": list, "dict": dict,
            "str": str, "int": int, "float": float, "round": round,
            "print": print, "Exception": Exception,
        },
        "_getattr_": getattr,                   # obj.method 허용
        "_getitem_": lambda obj, key: obj[key], # obj[key] 허용
        "_getiter_": iter,                      # for loop 등 반복 허용
        "_write_": _write_guard,                # 구문 할당(var = ...) 허용
        "_inplacevar_": lambda op, x, y: x + y if op == "+=" else x,
    }
    local_vars: dict = {}
    byte_code = compile_restricted(code, "<string>", "exec")
    exec(byte_code, restricted_globals, local_vars)
    return local_vars.get("result", {})


async def run_code_interpreter(state: AgentState) -> AgentState:
    file_path = state.get("uploaded_file_path")
    if not file_path:
        return state

    if file_path.endswith(".csv"):
        try:
            df = pd.read_csv(file_path, encoding="utf-8")
        except UnicodeDecodeError:
            df = pd.read_csv(file_path, encoding="cp949")
        df.columns = df.columns.astype(str).str.strip()
    else:
        df = pd.read_excel(file_path)
    
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
        "internal_data": result,
        "tool_calls": [{"tool": "code_interpreter", "status": "done"}],
    }
