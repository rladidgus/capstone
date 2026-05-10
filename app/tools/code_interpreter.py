"""
업로드된 CSV/XLSX를 분석하기 위해 LLM이 생성한 Pandas 코드를 실행합니다.
"""
import traceback
from typing import Any

import numpy as np
import pandas as pd
from RestrictedPython import compile_restricted, safe_globals

from app.agent.state import AgentState
from app.services.llm_service import LLMService

llm = LLMService()

CODE_GEN_PROMPT = """
다음 CSV 데이터를 Pandas로 분석하는 Python 코드를 작성하세요.
분석 요청: {request}
컬럼 정보: {columns}
표준화된 컬럼 정보: {standard_columns}

규칙:
- pandas를 pd로 import하여 사용
- 데이터프레임 변수명은 df를 사용
- 표준화된 컬럼이 있으면 sold_at, sales_date, hour, day_of_week, amount, quantity, menu, category 컬럼을 우선 사용
- 결과를 result 변수에 dict 형태로 저장
- result에는 가능하면 total_amount, avg_daily_amount, time_series, top_menus, hourly_sales를 포함
- print 사용 금지
- 외부 라이브러리 import 금지 (pandas, numpy 제외)

Python 코드만 출력하세요 (마크다운 코드블록 없이):
"""

COLUMN_ALIASES = {
    "sold_at": ["sold_at", "일시", "결제일시", "기본판매일시", "판매일시", "날짜", "date", "datetime"],
    "amount": ["amount", "매출액", "결제금액", "합계금액", "총실매출금액", "sales", "price", "total"],
    "quantity": ["quantity", "수량", "판매수량", "qty"],
    "menu": ["menu", "메뉴", "상품명", "상품", "item", "product"],
    "category": ["category", "카테고리", "대분류명", "분류"],
}


def _read_sales_file(file_path: str) -> pd.DataFrame:
    if file_path.endswith(".csv"):
        try:
            df = pd.read_csv(file_path, encoding="utf-8-sig")
        except UnicodeDecodeError:
            df = pd.read_csv(file_path, encoding="cp949")
    else:
        df = pd.read_excel(file_path)

    df.columns = df.columns.astype(str).str.strip()
    df = df.loc[:, ~df.columns.str.match(r"^Unnamed")]
    df = df.dropna(how="all")
    return df


def _find_column(df: pd.DataFrame, aliases: list[str]) -> str | None:
    normalized = {str(column).strip().lower(): column for column in df.columns}
    for alias in aliases:
        found = normalized.get(alias.lower())
        if found is not None:
            return found
    return None


def _normalize_sales_dataframe(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, str]]:
    normalized = df.copy()
    mapped_columns: dict[str, str] = {}

    for target, aliases in COLUMN_ALIASES.items():
        source = _find_column(normalized, aliases)
        if source is not None:
            mapped_columns[target] = str(source)
            if target not in normalized.columns:
                normalized[target] = normalized[source]

    if "sold_at" in normalized.columns:
        normalized["sold_at"] = pd.to_datetime(normalized["sold_at"], errors="coerce")
        normalized["sales_date"] = normalized["sold_at"].dt.date
        normalized["hour"] = normalized["sold_at"].dt.hour
        normalized["day_of_week"] = normalized["sold_at"].dt.dayofweek

    if "amount" in normalized.columns:
        normalized["amount"] = (
            normalized["amount"]
            .astype(str)
            .str.replace(",", "", regex=False)
            .str.replace("원", "", regex=False)
            .str.strip()
        )
        normalized["amount"] = pd.to_numeric(normalized["amount"], errors="coerce").fillna(0)

    if "quantity" in normalized.columns:
        normalized["quantity"] = pd.to_numeric(normalized["quantity"], errors="coerce").fillna(1).astype(int)
    else:
        normalized["quantity"] = 1

    if "menu" not in normalized.columns:
        normalized["menu"] = "알수없음"
    else:
        normalized["menu"] = normalized["menu"].fillna("알수없음").astype(str)

    if "category" not in normalized.columns:
        normalized["category"] = "기타"
    else:
        normalized["category"] = normalized["category"].fillna("기타").astype(str)

    return normalized, mapped_columns


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, tuple):
        return [_json_safe(v) for v in value]
    if isinstance(value, (pd.Timestamp,)):
        return value.isoformat()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    if pd.isna(value) if not isinstance(value, (list, dict, tuple)) else False:
        return None
    return value


def _build_rule_based_summary(df: pd.DataFrame, mapped_columns: dict[str, str]) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "source": "rule_based_summary",
        "row_count": int(len(df)),
        "columns": [str(column) for column in df.columns],
        "mapped_columns": mapped_columns,
        "warnings": [],
    }

    if "amount" not in df.columns:
        summary["warnings"].append("매출 금액 컬럼을 찾지 못했습니다.")
        return summary

    valid_amount = df["amount"].fillna(0)
    summary["total_amount"] = float(valid_amount.sum())
    summary["avg_order_amount"] = float(valid_amount.mean()) if len(valid_amount) else 0.0
    summary["total_quantity"] = int(df["quantity"].sum()) if "quantity" in df.columns else int(len(df))

    if "sales_date" in df.columns:
        dated = df.dropna(subset=["sales_date"])
        if not dated.empty:
            daily = (
                dated.groupby("sales_date")["amount"]
                .sum()
                .reset_index()
                .sort_values("sales_date")
            )
            summary["time_series"] = [
                {"date": str(row["sales_date"]), "amount": float(row["amount"])}
                for _, row in daily.iterrows()
            ]
            summary["avg_daily_amount"] = float(daily["amount"].mean())
            summary["period_start"] = str(daily["sales_date"].min())
            summary["period_end"] = str(daily["sales_date"].max())

    if "hour" in df.columns:
        hourly_source = df.dropna(subset=["hour"])
        if not hourly_source.empty:
            hourly = (
                hourly_source.groupby("hour")["amount"]
                .sum()
                .reset_index()
                .sort_values("hour")
            )
            summary["hourly_sales"] = [
                {"hour": int(row["hour"]), "amount": float(row["amount"])}
                for _, row in hourly.iterrows()
            ]
            summary["peak_hour"] = int(hourly.loc[hourly["amount"].idxmax(), "hour"])

    if "menu" in df.columns:
        menu = (
            df.groupby("menu")["amount"]
            .sum()
            .sort_values(ascending=False)
            .head(5)
            .reset_index()
        )
        summary["top_menus"] = [
            {"menu": str(row["menu"]), "amount": float(row["amount"])}
            for _, row in menu.iterrows()
        ]

    if "category" in df.columns:
        category = (
            df.groupby("category")["amount"]
            .sum()
            .sort_values(ascending=False)
            .reset_index()
        )
        summary["category_sales"] = [
            {"category": str(row["category"]), "amount": float(row["amount"])}
            for _, row in category.iterrows()
        ]

    return summary


def _strip_code_fence(code: str) -> str:
    stripped = code.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines).strip()
    return stripped


def _run_safe(code: str, df: pd.DataFrame) -> dict[str, Any]:
    def _write_guard(obj):
        return obj  # 안전장치를 통과시키는 더미 래퍼

    restricted_globals = {
        **safe_globals,
        "pd": pd,
        "np": np,
        "df": df,
        "__builtins__": {
            "len": len, "range": range, "list": list, "dict": dict,
            "str": str, "int": int, "float": float, "round": round,
            "sum": sum, "min": min, "max": max, "abs": abs,
            "enumerate": enumerate, "zip": zip, "sorted": sorted,
            "print": print, "Exception": Exception, "ValueError": ValueError,
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

    try:
        raw_df = _read_sales_file(file_path)
        df, mapped_columns = _normalize_sales_dataframe(raw_df)
    except Exception:
        return {
            "internal_data": {
                "source": "code_interpreter",
                "error": "업로드 파일을 읽는 중 오류가 발생했습니다.",
                "debug_error": traceback.format_exc(),
            },
            "tool_calls": [{"tool": "code_interpreter", "status": "failed"}],
        }

    fallback_result = _build_rule_based_summary(df, mapped_columns)

    if state.get("mode") == "quick":
        result = {
            **fallback_result,
            "source": "rule_based_summary",
            "code_status": "skipped_quick_mode",
        }
        return {
            "internal_data": _json_safe(result),
            "tool_calls": [{
                "tool": "code_interpreter",
                "status": "skipped_quick_mode",
                "fallback_available": True,
            }],
        }
    
    columns_info = df.dtypes.to_dict()

    prompt = CODE_GEN_PROMPT.format(
        request=state["user_query"],
        columns={k: str(v) for k, v in columns_info.items()},
        standard_columns=[column for column in ["sold_at", "sales_date", "hour", "day_of_week", "amount", "quantity", "menu", "category"] if column in df.columns],
    )
    generated_code = ""

    try:
        generated_code = _strip_code_fence(await llm.generate_text(prompt))
        llm_result = _run_safe(generated_code, df)
        result = {
            **fallback_result,
            **(_json_safe(llm_result) if isinstance(llm_result, dict) else {}),
            "source": "llm_code_interpreter",
            "fallback_summary": fallback_result,
            "code_status": "success",
        }
    except Exception:
        result = {
            **fallback_result,
            "source": "rule_based_summary",
            "code_status": "failed",
            "code_error": traceback.format_exc(),
            "generated_code": generated_code,
        }

    return {
        "internal_data": _json_safe(result),
        "tool_calls": [{
            "tool": "code_interpreter",
            "status": result.get("code_status", "done"),
            "fallback_available": True,
        }],
    }
