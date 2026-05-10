"""Benchmark Ollama generation models for ViewPoint agent tasks."""
import argparse
import asyncio
import json
import time
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
import httpx


SAMPLE_INTERNAL_DATA = {
    "source": "rule_based_summary",
    "row_count": 84,
    "total_amount": 792730.0,
    "avg_daily_amount": 113247.14,
    "peak_hour": 18,
    "time_series": [
        {"date": "2026-05-05", "amount": 100240},
        {"date": "2026-05-06", "amount": 108360},
        {"date": "2026-05-07", "amount": 112430},
        {"date": "2026-05-08", "amount": 119780},
        {"date": "2026-05-09", "amount": 128950},
        {"date": "2026-05-10", "amount": 121540},
        {"date": "2026-05-11", "amount": 101430},
    ],
    "top_menus": [
        {"menu": "샌드위치", "amount": 260000},
        {"menu": "라떼", "amount": 210000},
        {"menu": "아메리카노", "amount": 180000},
    ],
    "hourly_sales": [
        {"hour": 11, "amount": 101000},
        {"hour": 12, "amount": 132000},
        {"hour": 18, "amount": 188000},
        {"hour": 19, "amount": 160000},
    ],
}

SAMPLE_EXTERNAL_DATA = {
    "weather": {
        "source": "KMA ASOS daily observation",
        "condition": "rainy",
        "temperature_c": 13.4,
        "rainfall_mm": 0.8,
    },
    "subway": {
        "source": "Seoul Open Data CardSubwayStatsNew",
        "date_scope": "exact",
        "total_passenger_count": 170518,
    },
    "price_index": {
        "source": "Bank of Korea ECOS",
        "indicators": {
            "consumer_price_index": {"latest": {"value": 116.3}},
            "base_rate": {"latest": {"value": 3.0}},
        },
    },
    "missing_fields": [],
}


PROMPTS = {
    "planner_quick": """
항상 유효한 JSON 형식으로만 응답하세요. 마크다운 코드블록 없이 순수 JSON만 출력하세요.

당신은 소상공인 경영 분석 전문가입니다.
사용자의 질문에 대해 핵심 가설 1~2개와 간단한 분석 계획을 수립하세요.
빠른 브리핑이 목적이므로 가장 중요한 요인에만 집중하세요.

사용자 질문: 최근 일주일 매출이 왜 변했는지 분석해줘
분석 기간: 2026-05-05~2026-05-11

다음 JSON 형식으로 응답하세요:
{
  "hypotheses": ["핵심 가설1", "핵심 가설2"],
  "analysis_plan": ["단계1", "단계2"]
}
""",
    "reporter_quick": f"""
항상 유효한 JSON 형식으로만 응답하세요. 마크다운 코드블록 없이 순수 JSON만 출력하세요.

당신은 소상공인 경영 분석 전문가입니다.
아래 분석 결과를 바탕으로 핵심만 담은 간결한 브리핑을 작성하세요.
요약 2문장, 주요 원인 1~2개, 즉시 실행 가능한 개선안 2~3개에만 집중하세요.

사용자 질문: 최근 일주일 매출이 왜 변했는지 분석해줘
내부 데이터: {json.dumps(SAMPLE_INTERNAL_DATA, ensure_ascii=False)}
외부 데이터: {json.dumps(SAMPLE_EXTERNAL_DATA, ensure_ascii=False)}
통계 요약: 매출 추세 변화율은 +12.4%이며, 18시 매출 집중도가 가장 높습니다.
경영 메모 맥락: 최근 비 오는 날에는 따뜻한 음료와 샌드위치 세트 판매가 증가했습니다.

다음 JSON 형식으로 응답하세요:
{{
  "summary": "핵심 요약",
  "analysis_details": [
    {{"factor": "주요 요인", "impact": "긍정적|부정적|중립", "description": "한 줄 설명"}}
  ],
  "action_items": ["즉시 실행방안1", "즉시 실행방안2"],
  "chart_data": {{
    "type": "line",
    "categories": ["2026-05-05"],
    "series": [{{"name": "매출", "data": [100240]}}]
  }}
}}
""",
    "code_generation": """
다음 CSV 데이터를 Pandas로 분석하는 Python 코드를 작성하세요.
분석 요청: 최근 일주일 매출 추이, 인기 메뉴, 시간대별 매출을 분석해줘
컬럼 정보: {"sold_at": "datetime64[ns]", "amount": "float64", "quantity": "int64", "menu": "object", "category": "object"}
표준화된 컬럼 정보: ["sold_at", "sales_date", "hour", "day_of_week", "amount", "quantity", "menu", "category"]

규칙:
- pandas를 pd로 import하여 사용
- 데이터프레임 변수명은 df를 사용
- 결과를 result 변수에 dict 형태로 저장
- result에는 total_amount, avg_daily_amount, time_series, top_menus, hourly_sales를 포함
- print 사용 금지
- 외부 라이브러리 import 금지

Python 코드만 출력하세요. 마크다운 코드블록 없이 출력하세요.
""",
}

REQUIRED_KEYS = {
    "planner_quick": ["hypotheses", "analysis_plan"],
    "reporter_quick": ["summary", "analysis_details", "action_items", "chart_data"],
}


def _extract_json(text: str) -> tuple[dict[str, Any] | None, str | None]:
    try:
        start = text.find("{")
        end = text.rfind("}") + 1
        if start < 0 or end <= start:
            return None, "JSON object not found"
        return json.loads(text[start:end]), None
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"


def _score_text(task: str, text: str, parsed: dict[str, Any] | None) -> int:
    if task == "code_generation":
        score = 1
        if "result" in text:
            score += 1
        if "time_series" in text and "top_menus" in text:
            score += 1
        if "```" not in text and "print(" not in text:
            score += 1
        if "import os" not in text and "open(" not in text:
            score += 1
        return min(score, 5)

    if not parsed:
        return 1
    score = 3
    if task == "reporter_quick":
        actions = parsed.get("action_items") or []
        details = parsed.get("analysis_details") or []
        if len(actions) >= 2:
            score += 1
        if details and parsed.get("chart_data"):
            score += 1
    elif task == "planner_quick":
        if len(parsed.get("hypotheses") or []) >= 1 and len(parsed.get("analysis_plan") or []) >= 2:
            score += 1
    return min(score, 5)


async def _generate(base_url: str, model: str, prompt: str, max_tokens: int) -> str:
    async with httpx.AsyncClient(timeout=180) as client:
        resp = await client.post(
            f"{base_url}/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.1,
                    "num_predict": max_tokens,
                    "num_ctx": 4096,
                },
                "keep_alive": "10m",
            },
        )
        resp.raise_for_status()
        return resp.json().get("response", "")


async def run_benchmark(model: str, base_url: str) -> list[dict[str, Any]]:
    results = []
    for task, prompt in PROMPTS.items():
        max_tokens = 512 if task != "reporter_quick" else 1024
        started = time.perf_counter()
        error = None
        text = ""
        try:
            text = await _generate(base_url, model, prompt, max_tokens=max_tokens)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
        elapsed = round(time.perf_counter() - started, 2)

        parsed = None
        json_error = None
        required_ok = None
        if task in REQUIRED_KEYS and text:
            parsed, json_error = _extract_json(text)
            required_ok = bool(parsed) and all(key in parsed for key in REQUIRED_KEYS[task])

        results.append(
            {
                "model": model,
                "task": task,
                "elapsed_seconds": elapsed,
                "json_success": parsed is not None if task in REQUIRED_KEYS else None,
                "required_keys": required_ok,
                "quality_score": _score_text(task, text, parsed),
                "error": error or json_error,
                "preview": text[:500].replace("\n", " "),
            }
        )
    return results


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="llama3.1:8b")
    parser.add_argument("--output", default="benchmark_results.json")
    args = parser.parse_args()

    load_dotenv(PROJECT_ROOT / ".env")
    import os

    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    results = await run_benchmark(args.model, base_url)

    output_path = PROJECT_ROOT / args.output
    output_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    for result in results:
        print(
            result["model"],
            result["task"],
            f"{result['elapsed_seconds']}s",
            "json=",
            result["json_success"],
            "keys=",
            result["required_keys"],
            "score=",
            result["quality_score"],
            "error=",
            result["error"],
        )
    print("saved:", output_path)


if __name__ == "__main__":
    asyncio.run(main())
