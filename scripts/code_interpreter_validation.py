"""Validate Code Interpreter fallback behavior without calling Ollama."""
import asyncio
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.tools import code_interpreter as ci


async def _run_with_stub(file_path: str, generated_code: str):
    async def fake_generate_text(*args, **kwargs):
        return generated_code

    original = ci.llm.generate_text
    ci.llm.generate_text = fake_generate_text
    try:
        return await ci.run_code_interpreter({
            "uploaded_file_path": file_path,
            "user_query": "매출 데이터를 분석해줘",
        })
    finally:
        ci.llm.generate_text = original


async def main() -> None:
    sample_files = sorted((PROJECT_ROOT / "data" / "uploads").glob("*.csv"))
    assert sample_files, "검증할 CSV 샘플 파일이 없습니다."

    success_code = """
result = {
    "llm_total_amount": float(df["amount"].sum()),
    "llm_row_count": int(len(df)),
}
"""
    for file_path in sample_files:
        success_state = await _run_with_stub(str(file_path), success_code)
        success_data = success_state["internal_data"]
        assert success_data["code_status"] == "success"
        assert success_data["total_amount"] > 0
        assert success_data["row_count"] > 0
        assert success_data.get("time_series")
        assert success_data.get("top_menus")

        failure_state = await _run_with_stub(str(file_path), "raise Exception('boom')")
        failure_data = failure_state["internal_data"]
        assert failure_data["code_status"] == "failed"
        assert failure_data["source"] == "rule_based_summary"
        assert failure_data["total_amount"] > 0
        assert failure_data.get("time_series")
        assert failure_data.get("generated_code")

        print(
            "validated:",
            file_path.name,
            "rows=",
            failure_data["row_count"],
            "total=",
            int(failure_data["total_amount"]),
        )

    print("code_interpreter_checks: OK")


if __name__ == "__main__":
    asyncio.run(main())
