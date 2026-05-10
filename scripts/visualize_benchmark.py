"""Create PPT-friendly benchmark artifacts from model benchmark JSON files.

Outputs:
- benchmark_summary.csv
- benchmark_e2e_summary.csv
- benchmark_response_time.svg
- benchmark_quality_score.svg
- benchmark_e2e_time.svg
- benchmark_e2e_quality.svg
- PNG versions when qlmanage conversion works
"""
import argparse
import csv
import html
import json
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]

COLORS = {
    "llama3.1:8b": "#2563eb",
    "mistral:7b": "#059669",
    "mistral-developer-analyzer:latest": "#c2410c",
}

MODEL_ORDER = [
    "llama3.1:8b",
    "mistral:7b",
    "mistral-developer-analyzer:latest",
]

TASK_ORDER = ["planner_quick", "reporter_quick", "code_generation"]

E2E_RESULTS = [
    {
        "model": "llama3.1:8b",
        "mode": "quick",
        "elapsed_seconds": 132.32,
        "completed": True,
        "report_data": True,
        "chart_data": True,
        "quality_score": 5,
        "memo": "E2E_OK, confidence_level=high, 전체 흐름 완료",
    },
    {
        "model": "llama3.1:8b",
        "mode": "quick_optimized",
        "elapsed_seconds": 49.81,
        "completed": True,
        "report_data": True,
        "chart_data": True,
        "quality_score": 5,
        "memo": "E2E_OK, planner/evaluator/code generation LLM 호출 축소 후 재측정",
    },
    {
        "model": "mistral:7b",
        "mode": "quick",
        "elapsed_seconds": 121.14,
        "completed": True,
        "report_data": True,
        "chart_data": True,
        "quality_score": 4,
        "memo": "E2E_OK, confidence_level=high, 전체 시간은 더 짧지만 단일 reporter 품질/속도는 llama 대비 약점",
    },
    {
        "model": "mistral-developer-analyzer:latest",
        "mode": "quick",
        "elapsed_seconds": 106.61,
        "completed": True,
        "report_data": True,
        "chart_data": True,
        "quality_score": 4,
        "memo": "E2E_OK, confidence_level=high, 총 시간은 가장 짧지만 단일 응답 품질/일관성 이슈 있음",
    },
    {
        "model": "llama3.1:8b",
        "mode": "deep",
        "elapsed_seconds": 149.75,
        "completed": True,
        "report_data": True,
        "chart_data": True,
        "quality_score": 5,
        "memo": "E2E_OK, confidence_level=high, quick 대비 약 17.43초 증가",
    },
    {
        "model": "mistral:7b",
        "mode": "deep",
        "elapsed_seconds": 132.21,
        "completed": True,
        "report_data": True,
        "chart_data": True,
        "quality_score": 4,
        "memo": "E2E_OK, confidence_level=high, llama deep 대비 약 17.54초 빠름",
    },
    {
        "model": "mistral-developer-analyzer:latest",
        "mode": "deep",
        "elapsed_seconds": 178.02,
        "completed": True,
        "report_data": True,
        "chart_data": True,
        "quality_score": 4,
        "memo": "E2E_OK, confidence_level=high, deep에서는 세 모델 중 가장 느림",
    },
]

MODE_ORDER = ["quick", "quick_optimized", "deep"]


def load_results(files: list[Path]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for file_path in files:
        data = json.loads(file_path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            continue
        rows.extend(row for row in data if isinstance(row, dict))

    rows.sort(
        key=lambda row: (
            MODEL_ORDER.index(row["model"]) if row.get("model") in MODEL_ORDER else 999,
            TASK_ORDER.index(row["task"]) if row.get("task") in TASK_ORDER else 999,
        )
    )
    return rows


def write_summary_csv(rows: list[dict[str, Any]], output_path: Path) -> None:
    with output_path.open("w", encoding="utf-8-sig", newline="") as fp:
        writer = csv.DictWriter(
            fp,
            fieldnames=[
                "model",
                "task",
                "elapsed_seconds",
                "json_success",
                "required_keys",
                "quality_score",
                "error",
                "preview",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({
                "model": row.get("model"),
                "task": row.get("task"),
                "elapsed_seconds": row.get("elapsed_seconds"),
                "json_success": row.get("json_success"),
                "required_keys": row.get("required_keys"),
                "quality_score": row.get("quality_score"),
                "error": row.get("error"),
                "preview": row.get("preview"),
            })


def write_e2e_summary_csv(rows: list[dict[str, Any]], output_path: Path) -> None:
    with output_path.open("w", encoding="utf-8-sig", newline="") as fp:
        writer = csv.DictWriter(
            fp,
            fieldnames=[
                "model",
                "mode",
                "elapsed_seconds",
                "completed",
                "report_data",
                "chart_data",
                "quality_score",
                "memo",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def grouped(rows: list[dict[str, Any]], metric: str) -> list[tuple[str, list[dict[str, Any]]]]:
    result = []
    for task in TASK_ORDER:
        task_rows = [row for row in rows if row.get("task") == task and row.get(metric) is not None]
        task_rows.sort(key=lambda row: MODEL_ORDER.index(row["model"]) if row.get("model") in MODEL_ORDER else 999)
        result.append((task, task_rows))
    return result


def grouped_by_mode(rows: list[dict[str, Any]], metric: str) -> list[tuple[str, list[dict[str, Any]]]]:
    result = []
    for mode in MODE_ORDER:
        mode_rows = [row for row in rows if row.get("mode") == mode and row.get(metric) is not None]
        mode_rows.sort(key=lambda row: MODEL_ORDER.index(row["model"]) if row.get("model") in MODEL_ORDER else 999)
        result.append((mode, mode_rows))
    return result


def draw_grouped_bar_svg(
    rows: list[dict[str, Any]],
    metric: str,
    title: str,
    subtitle: str,
    output_path: Path,
    max_value: float | None = None,
    value_suffix: str = "",
) -> None:
    width = 1400
    group_height = 210
    top = 120
    left = 310
    right = 90
    bar_height = 26
    row_gap = 18
    chart_width = width - left - right
    groups = grouped(rows, metric)
    height = top + len(groups) * group_height + 80

    values = [float(row[metric]) for _, task_rows in groups for row in task_rows]
    max_metric = max_value or (max(values) if values else 1)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#f7f8fa"/>',
        f'<text x="42" y="54" font-family="Arial, Apple SD Gothic Neo, sans-serif" font-size="32" font-weight="700" fill="#20242a">{html.escape(title)}</text>',
        f'<text x="42" y="86" font-family="Arial, Apple SD Gothic Neo, sans-serif" font-size="17" fill="#68717d">{html.escape(subtitle)}</text>',
    ]

    for group_index, (task, task_rows) in enumerate(groups):
        group_y = top + group_index * group_height
        task_label = task.replace("_", " ")
        parts.append(f'<text x="42" y="{group_y + 32}" font-family="Arial, Apple SD Gothic Neo, sans-serif" font-size="21" font-weight="700" fill="#20242a">{html.escape(task_label)}</text>')

        for row_index, row in enumerate(task_rows):
            y = group_y + 58 + row_index * (bar_height + row_gap)
            model = str(row.get("model"))
            value = float(row.get(metric) or 0)
            bar_width = 0 if max_metric == 0 else value / max_metric * chart_width
            color = COLORS.get(model, "#64748b")
            value_label = f"{value:.2f}{value_suffix}" if metric == "elapsed_seconds" else f"{value:.0f}{value_suffix}"

            parts.extend([
                f'<text x="58" y="{y + 19}" font-family="Arial, Apple SD Gothic Neo, sans-serif" font-size="16" fill="#374151">{html.escape(model)}</text>',
                f'<rect x="{left}" y="{y}" width="{chart_width}" height="{bar_height}" rx="13" fill="#e9edf3"/>',
                f'<rect x="{left}" y="{y}" width="{bar_width:.2f}" height="{bar_height}" rx="13" fill="{color}"/>',
                f'<text x="{left + chart_width + 16}" y="{y + 19}" font-family="Arial, Apple SD Gothic Neo, sans-serif" font-size="16" fill="#4b5563">{value_label}</text>',
            ])

        parts.append(f'<line x1="42" x2="{width - 42}" y1="{group_y + group_height - 28}" y2="{group_y + group_height - 28}" stroke="#d9dee6"/>')

    parts.append("</svg>")
    output_path.write_text("\n".join(parts), encoding="utf-8")


def draw_e2e_bar_svg(
    rows: list[dict[str, Any]],
    metric: str,
    title: str,
    subtitle: str,
    output_path: Path,
    max_value: float | None = None,
    value_suffix: str = "",
) -> None:
    width = 1400
    group_height = 210
    top = 120
    left = 310
    right = 90
    bar_height = 26
    row_gap = 18
    chart_width = width - left - right
    groups = grouped_by_mode(rows, metric)
    height = top + len(groups) * group_height + 80

    values = [float(row[metric]) for _, mode_rows in groups for row in mode_rows]
    max_metric = max_value or (max(values) if values else 1)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#f7f8fa"/>',
        f'<text x="42" y="54" font-family="Arial, Apple SD Gothic Neo, sans-serif" font-size="32" font-weight="700" fill="#20242a">{html.escape(title)}</text>',
        f'<text x="42" y="86" font-family="Arial, Apple SD Gothic Neo, sans-serif" font-size="17" fill="#68717d">{html.escape(subtitle)}</text>',
    ]

    for group_index, (mode, mode_rows) in enumerate(groups):
        group_y = top + group_index * group_height
        parts.append(f'<text x="42" y="{group_y + 32}" font-family="Arial, Apple SD Gothic Neo, sans-serif" font-size="21" font-weight="700" fill="#20242a">{html.escape(mode.upper())}</text>')

        for row_index, row in enumerate(mode_rows):
            y = group_y + 58 + row_index * (bar_height + row_gap)
            model = str(row.get("model"))
            value = float(row.get(metric) or 0)
            bar_width = 0 if max_metric == 0 else value / max_metric * chart_width
            color = COLORS.get(model, "#64748b")
            value_label = f"{value:.2f}{value_suffix}" if metric == "elapsed_seconds" else f"{value:.0f}{value_suffix}"

            parts.extend([
                f'<text x="58" y="{y + 19}" font-family="Arial, Apple SD Gothic Neo, sans-serif" font-size="16" fill="#374151">{html.escape(model)}</text>',
                f'<rect x="{left}" y="{y}" width="{chart_width}" height="{bar_height}" rx="13" fill="#e9edf3"/>',
                f'<rect x="{left}" y="{y}" width="{bar_width:.2f}" height="{bar_height}" rx="13" fill="{color}"/>',
                f'<text x="{left + chart_width + 16}" y="{y + 19}" font-family="Arial, Apple SD Gothic Neo, sans-serif" font-size="16" fill="#4b5563">{value_label}</text>',
            ])

        parts.append(f'<line x1="42" x2="{width - 42}" y1="{group_y + group_height - 28}" y2="{group_y + group_height - 28}" stroke="#d9dee6"/>')

    parts.append("</svg>")
    output_path.write_text("\n".join(parts), encoding="utf-8")


def convert_svg_to_png(svg_path: Path, output_dir: Path) -> Path | None:
    if not shutil.which("qlmanage"):
        return None

    try:
        subprocess.run(
            ["qlmanage", "-t", "-s", "1600", "-o", str(output_dir), str(svg_path)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        return None

    generated = output_dir / f"{svg_path.name}.png"
    final = svg_path.with_suffix(".png")
    if generated.exists():
        generated.replace(final)
        return final
    return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--inputs",
        nargs="*",
        default=[
            "benchmark_results_llama3.1_8b.json",
            "benchmark_results_mistral_7b.json",
            "benchmark_results_mistral_developer_analyzer_latest.json",
        ],
    )
    parser.add_argument("--output-dir", default="benchmark_artifacts")
    args = parser.parse_args()

    input_files = [PROJECT_ROOT / item for item in args.inputs]
    missing = [str(path) for path in input_files if not path.exists()]
    if missing:
        print("Missing input files:", ", ".join(missing), file=sys.stderr)
        raise SystemExit(1)

    output_dir = PROJECT_ROOT / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    rows = load_results(input_files)
    summary_csv = output_dir / "benchmark_summary.csv"
    e2e_summary_csv = output_dir / "benchmark_e2e_summary.csv"
    response_svg = output_dir / "benchmark_response_time.svg"
    quality_svg = output_dir / "benchmark_quality_score.svg"
    e2e_time_svg = output_dir / "benchmark_e2e_time.svg"
    e2e_quality_svg = output_dir / "benchmark_e2e_quality.svg"

    write_summary_csv(rows, summary_csv)
    write_e2e_summary_csv(E2E_RESULTS, e2e_summary_csv)
    draw_grouped_bar_svg(
        rows,
        metric="elapsed_seconds",
        title="모델별 응답 시간 비교",
        subtitle="낮을수록 빠름. 단일 프롬프트 기준.",
        output_path=response_svg,
        value_suffix="s",
    )
    draw_grouped_bar_svg(
        rows,
        metric="quality_score",
        title="모델별 품질 점수 비교",
        subtitle="높을수록 좋음. 5점 만점.",
        output_path=quality_svg,
        max_value=5,
        value_suffix="/5",
    )
    draw_e2e_bar_svg(
        E2E_RESULTS,
        metric="elapsed_seconds",
        title="E2E 실행 시간 비교",
        subtitle="낮을수록 빠름. 업로드 파일부터 리포트 조회까지 전체 흐름 기준.",
        output_path=e2e_time_svg,
        value_suffix="s",
    )
    draw_e2e_bar_svg(
        E2E_RESULTS,
        metric="quality_score",
        title="E2E 품질 점수 비교",
        subtitle="높을수록 좋음. report_data/chart_data 생성 및 리포트 안정성 기준.",
        output_path=e2e_quality_svg,
        max_value=5,
        value_suffix="/5",
    )

    generated = [summary_csv, e2e_summary_csv, response_svg, quality_svg, e2e_time_svg, e2e_quality_svg]
    for svg in [response_svg, quality_svg, e2e_time_svg, e2e_quality_svg]:
        png = convert_svg_to_png(svg, output_dir)
        if png:
            generated.append(png)

    for path in generated:
        print(path.relative_to(PROJECT_ROOT))


if __name__ == "__main__":
    main()
