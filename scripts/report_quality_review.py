"""Review recent generated reports and export a quality summary.

This script checks report JSON structure, chart validity, action item quality,
and obvious consistency risks. It is intentionally lightweight so the review
can be repeated after model or graph changes.
"""
import argparse
import asyncio
import csv
import json
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from sqlalchemy import select

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv(PROJECT_ROOT / ".env")

from app.db.database import AsyncSessionLocal
from app.models.report import ReportORM


REQUIRED_DETAIL_KEYS = {"factor", "impact", "description"}
ALLOWED_IMPACTS = {"긍정적", "부정적", "중립"}
RISK_TERMS = ["예시", "임의", "가정", "확실히", "반드시", "알 수 없음", "N/A"]


def _safe_len(value: Any) -> int:
    return len(value) if isinstance(value, list) else 0


def _is_numeric_list(values: Any) -> bool:
    if not isinstance(values, list) or not values:
        return False
    for value in values:
        try:
            float(value)
        except (TypeError, ValueError):
            return False
    return True


def _chart_valid(chart_data: Any) -> tuple[bool, str]:
    if not isinstance(chart_data, dict):
        return False, "chart_data is not an object"

    categories = chart_data.get("categories")
    series = chart_data.get("series")
    if not isinstance(categories, list) or not categories:
        return False, "categories missing"
    if not isinstance(series, list) or not series:
        return False, "series missing"

    for item in series:
        if not isinstance(item, dict):
            return False, "series item is not an object"
        if not item.get("name"):
            return False, "series name missing"
        if not _is_numeric_list(item.get("data")):
            return False, "series data is not numeric"
    return True, "ok"


def _review_report(report: ReportORM) -> dict[str, Any]:
    data = report.report_data or {}
    chart_data = report.chart_data or {}
    details = data.get("analysis_details")
    action_items = data.get("action_items")
    summary = data.get("summary")

    issues: list[str] = []
    score = 5

    if not isinstance(summary, str) or len(summary.strip()) < 20:
        issues.append("summary가 너무 짧거나 없음")
        score -= 1

    if not isinstance(details, list) or not details:
        issues.append("analysis_details가 없음")
        score -= 1
    else:
        for index, detail in enumerate(details, start=1):
            if not isinstance(detail, dict):
                issues.append(f"analysis_details[{index}] 형식 오류")
                score -= 1
                continue
            missing = REQUIRED_DETAIL_KEYS - set(detail.keys())
            if missing:
                issues.append(f"analysis_details[{index}] 필수 키 누락: {sorted(missing)}")
                score -= 1
            if detail.get("impact") not in ALLOWED_IMPACTS:
                issues.append(f"analysis_details[{index}] impact 값 오류")
                score -= 1
            if len(str(detail.get("description", "")).strip()) < 20:
                issues.append(f"analysis_details[{index}] 설명이 짧음")
                score -= 1

    if not isinstance(action_items, list) or len(action_items) < 2:
        issues.append("action_items가 2개 미만")
        score -= 1
    else:
        too_short = [item for item in action_items if len(str(item).strip()) < 10]
        if too_short:
            issues.append("일부 action_items가 너무 짧음")
            score -= 1

    chart_ok, chart_reason = _chart_valid(chart_data)
    if not chart_ok:
        issues.append(f"chart_data 오류: {chart_reason}")
        score -= 1

    serialized = json.dumps(data, ensure_ascii=False)
    risk_terms = [term for term in RISK_TERMS if term in serialized]
    if risk_terms:
        issues.append(f"주의 표현 포함: {', '.join(risk_terms)}")
        score -= 1

    if report.status != "completed":
        issues.append(f"status가 completed가 아님: {report.status}")
        score -= 2

    score = max(score, 0)
    return {
        "report_id": str(report.report_id),
        "mode": report.mode,
        "status": report.status,
        "created_at": report.created_at.isoformat() if report.created_at else "",
        "completed_at": report.completed_at.isoformat() if report.completed_at else "",
        "confidence_level": report.confidence_level,
        "summary_length": len(summary or "") if isinstance(summary, str) else 0,
        "analysis_detail_count": _safe_len(details),
        "action_item_count": _safe_len(action_items),
        "chart_valid": chart_ok,
        "quality_score": score,
        "issues": "; ".join(issues) if issues else "없음",
        "summary": summary or "",
        "action_items": action_items if isinstance(action_items, list) else [],
        "analysis_details": details if isinstance(details, list) else [],
    }


async def _load_reports(limit: int, mode: str | None = None, query_contains: str | None = None) -> list[ReportORM]:
    async with AsyncSessionLocal() as db:
        statement = select(ReportORM)
        if mode:
            statement = statement.where(ReportORM.mode == mode)
        if query_contains:
            statement = statement.where(ReportORM.user_query.contains(query_contains))
        statement = statement.order_by(ReportORM.created_at.desc()).limit(limit)
        result = await db.execute(statement)
        return list(result.scalars().all())


def _write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as fp:
        writer = csv.DictWriter(
            fp,
            fieldnames=[
                "report_id",
                "mode",
                "status",
                "created_at",
                "completed_at",
                "confidence_level",
                "summary_length",
                "analysis_detail_count",
                "action_item_count",
                "chart_valid",
                "quality_score",
                "issues",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key) for key in writer.fieldnames})


def _write_markdown(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# 리포트 품질 검수 결과",
        "",
        "## 요약",
        "",
        "| report_id | mode | score | chart | details | actions | issues |",
        "|---|---:|---:|---|---:|---:|---|",
    ]
    for row in rows:
        lines.append(
            f"| `{row['report_id']}` | {row['mode']} | {row['quality_score']}/5 | "
            f"{'OK' if row['chart_valid'] else 'FAIL'} | {row['analysis_detail_count']} | "
            f"{row['action_item_count']} | {row['issues']} |"
        )

    lines.extend(["", "## 샘플 본문", ""])
    for row in rows:
        lines.extend([
            f"### {row['mode']} - {row['quality_score']}/5",
            "",
            f"- report_id: `{row['report_id']}`",
            f"- confidence: `{row['confidence_level']}`",
            f"- issues: {row['issues']}",
            "",
            "**Summary**",
            "",
            str(row["summary"]).strip() or "(없음)",
            "",
            "**Analysis Details**",
            "",
        ])
        for detail in row["analysis_details"]:
            if isinstance(detail, dict):
                lines.append(
                    f"- {detail.get('factor', '요인 없음')} / {detail.get('impact', '영향 없음')}: "
                    f"{detail.get('description', '')}"
                )
        lines.extend(["", "**Action Items**", ""])
        for item in row["action_items"]:
            lines.append(f"- {item}")
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=12)
    parser.add_argument("--output-dir", default="benchmark_artifacts")
    parser.add_argument("--mode", choices=["quick", "deep"])
    parser.add_argument("--query-contains")
    parser.add_argument("--prefix", default="report_quality_review")
    args = parser.parse_args()

    reports = await _load_reports(args.limit, mode=args.mode, query_contains=args.query_contains)
    rows = [_review_report(report) for report in reports]

    output_dir = PROJECT_ROOT / args.output_dir
    csv_path = output_dir / f"{args.prefix}.csv"
    md_path = output_dir / f"{args.prefix}.md"
    _write_csv(rows, csv_path)
    _write_markdown(rows, md_path)

    print(csv_path.relative_to(PROJECT_ROOT))
    print(md_path.relative_to(PROJECT_ROOT))
    for row in rows[:5]:
        print(
            f"{row['mode']} {row['quality_score']}/5 "
            f"chart={'OK' if row['chart_valid'] else 'FAIL'} issues={row['issues']}"
        )


if __name__ == "__main__":
    asyncio.run(main())
