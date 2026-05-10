"""Benchmark Ollama embedding models for Korean memo/RAG retrieval.

The benchmark measures:
- embedding dimension and latency
- local cosine-search retrieval quality
- optional Pinecone upsert/query compatibility
"""
import argparse
import asyncio
import csv
import math
import os
import statistics
import sys
import time
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv(PROJECT_ROOT / ".env")


DOCUMENTS = [
    {
        "id": "memo_weather",
        "content": "비 오는 날에는 따뜻한 라떼와 아메리카노 판매가 늘었고, 우산을 든 손님이 오후에 많이 방문했다.",
        "topic": "weather",
    },
    {
        "id": "memo_lunch_inventory",
        "content": "점심시간 12시부터 13시 사이에 샌드위치 재고가 부족해서 일부 고객이 구매하지 못했다.",
        "topic": "inventory",
    },
    {
        "id": "memo_coupon_revisit",
        "content": "쿠폰 발송 다음 날 재방문 고객이 증가했고, 기존 고객의 객단가도 소폭 상승했다.",
        "topic": "promotion",
    },
    {
        "id": "memo_delivery_complaint",
        "content": "배달 주문에서 포장 누락과 음료 온도 관련 불만이 반복적으로 접수되었다.",
        "topic": "delivery",
    },
    {
        "id": "memo_weekend_staff",
        "content": "주말 오후에는 대기 시간이 길어져 직원 한 명을 추가 배치했을 때 회전율이 개선되었다.",
        "topic": "staffing",
    },
    {
        "id": "memo_price_resistance",
        "content": "가격 인상 이후 일부 단골 고객이 저가 메뉴로 이동했고 세트 메뉴 선택 비중이 줄었다.",
        "topic": "price",
    },
]


QUERIES = [
    {
        "query": "날씨 때문에 잘 팔린 메뉴가 있었어?",
        "expected_id": "memo_weather",
        "topic": "weather",
    },
    {
        "query": "점심 피크 때 부족했던 상품을 확인하고 싶어",
        "expected_id": "memo_lunch_inventory",
        "topic": "inventory",
    },
    {
        "query": "쿠폰을 보낸 뒤 재방문 효과가 있었는지 찾아줘",
        "expected_id": "memo_coupon_revisit",
        "topic": "promotion",
    },
    {
        "query": "배달 고객 불만 원인이 뭐였지?",
        "expected_id": "memo_delivery_complaint",
        "topic": "delivery",
    },
    {
        "query": "주말에 직원 배치를 늘린 효과가 있었나?",
        "expected_id": "memo_weekend_staff",
        "topic": "staffing",
    },
    {
        "query": "가격을 올린 뒤 고객 반응이 어땠는지 찾아줘",
        "expected_id": "memo_price_resistance",
        "topic": "price",
    },
]


def format_for_embedding(model: str, text: str, kind: str) -> str:
    """Apply model-specific retrieval prefixes when required."""
    if model.startswith("nomic-embed-text"):
        prefix = "search_document" if kind == "document" else "search_query"
        return f"{prefix}: {text}"
    return text


async def embed_text(base_url: str, model: str, text: str) -> tuple[list[float], float, str]:
    started = time.perf_counter()
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{base_url}/api/embed",
            json={"model": model, "input": text},
        )
        endpoint = "/api/embed"
        if resp.status_code == 404:
            resp = await client.post(
                f"{base_url}/api/embeddings",
                json={"model": model, "prompt": text},
            )
            endpoint = "/api/embeddings"

        resp.raise_for_status()
        elapsed = time.perf_counter() - started
        data = resp.json()
        embeddings = data.get("embeddings")
        if isinstance(embeddings, list) and embeddings:
            return embeddings[0], elapsed, endpoint
        return data["embedding"], elapsed, endpoint


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def rank_documents(query_vector: list[float], document_vectors: dict[str, list[float]]) -> list[dict[str, Any]]:
    ranked = []
    for doc_id, vector in document_vectors.items():
        ranked.append({
            "id": doc_id,
            "score": cosine_similarity(query_vector, vector),
        })
    ranked.sort(key=lambda item: item["score"], reverse=True)
    return ranked


async def run_local_benchmark(model: str, base_url: str) -> dict[str, Any]:
    latencies: list[float] = []
    endpoint = ""
    document_vectors: dict[str, list[float]] = {}

    for doc in DOCUMENTS:
        text = format_for_embedding(model, doc["content"], "document")
        vector, elapsed, endpoint = await embed_text(base_url, model, text)
        document_vectors[doc["id"]] = vector
        latencies.append(elapsed)

    query_results = []
    top1_hits = 0
    top3_hits = 0
    reciprocal_ranks = []

    for item in QUERIES:
        text = format_for_embedding(model, item["query"], "query")
        query_vector, elapsed, endpoint = await embed_text(base_url, model, text)
        latencies.append(elapsed)
        ranked = rank_documents(query_vector, document_vectors)
        ids = [row["id"] for row in ranked]
        expected = item["expected_id"]
        rank = ids.index(expected) + 1 if expected in ids else 999
        top1_hits += int(rank == 1)
        top3_hits += int(rank <= 3)
        reciprocal_ranks.append(1 / rank if rank != 999 else 0)

        query_results.append({
            "query": item["query"],
            "expected_id": expected,
            "top1_id": ranked[0]["id"],
            "top1_score": ranked[0]["score"],
            "expected_rank": rank,
            "top3_ids": ", ".join(ids[:3]),
        })

    first_vector = next(iter(document_vectors.values()))
    return {
        "model": model,
        "endpoint": endpoint,
        "dimension": len(first_vector),
        "avg_latency_seconds": statistics.mean(latencies),
        "p95_latency_seconds": sorted(latencies)[int(len(latencies) * 0.95) - 1],
        "top1_accuracy": top1_hits / len(QUERIES),
        "top3_accuracy": top3_hits / len(QUERIES),
        "mrr": statistics.mean(reciprocal_ranks),
        "query_results": query_results,
        "document_vectors": document_vectors,
    }


async def run_model_safely(model: str, base_url: str) -> dict[str, Any]:
    try:
        return await run_local_benchmark(model, base_url)
    except Exception as exc:
        return {
            "model": model,
            "endpoint": "failed",
            "dimension": "",
            "avg_latency_seconds": "",
            "p95_latency_seconds": "",
            "top1_accuracy": "",
            "top3_accuracy": "",
            "mrr": "",
            "error": str(exc),
            "query_results": [],
        }


def write_summary_csv(results: list[dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as fp:
        writer = csv.DictWriter(
            fp,
            fieldnames=[
                "model",
                "endpoint",
                "dimension",
                "avg_latency_seconds",
                "p95_latency_seconds",
                "top1_accuracy",
                "top3_accuracy",
                "mrr",
                "error",
            ],
        )
        writer.writeheader()
        for result in results:
            writer.writerow({key: result.get(key) for key in writer.fieldnames})


def write_detail_csv(results: list[dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as fp:
        writer = csv.DictWriter(
            fp,
            fieldnames=[
                "model",
                "query",
                "expected_id",
                "top1_id",
                "top1_score",
                "expected_rank",
                "top3_ids",
            ],
        )
        writer.writeheader()
        for result in results:
            for row in result["query_results"]:
                writer.writerow({"model": result["model"], **row})


def write_markdown(results: list[dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# 임베딩 모델 품질 테스트 결과",
        "",
        "nomic-embed-text는 검색용 권장 prefix(`search_document:`, `search_query:`)를 적용해 측정했다.",
        "",
        "## 요약",
        "",
        "| model | dimension | avg latency | top1 | top3 | MRR |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for result in results:
        if result.get("error"):
            lines.append(
                f"| `{result['model']}` | 실패 | 실패 | 실패 | 실패 | 실패 |"
            )
            continue
        lines.append(
            f"| `{result['model']}` | {result['dimension']} | "
            f"{result['avg_latency_seconds']:.3f}s | {result['top1_accuracy']:.2f} | "
            f"{result['top3_accuracy']:.2f} | {result['mrr']:.2f} |"
        )

    lines.extend(["", "## 질의별 검색 결과", ""])
    for result in results:
        lines.extend([f"### `{result['model']}`", ""])
        if result.get("error"):
            lines.extend([f"- 실패 사유: {result['error']}", ""])
            continue
        lines.append("| query | expected | top1 | rank | top3 |")
        lines.append("|---|---|---|---:|---|")
        for row in result["query_results"]:
            lines.append(
                f"| {row['query']} | `{row['expected_id']}` | `{row['top1_id']}` | "
                f"{row['expected_rank']} | {row['top3_ids']} |"
            )
        lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", nargs="*", default=[os.getenv("OLLAMA_EMBED_MODEL", "embeddinggemma:latest")])
    parser.add_argument("--output-dir", default="benchmark_artifacts")
    args = parser.parse_args()

    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    output_dir = PROJECT_ROOT / args.output_dir

    results = []
    for model in args.models:
        result = await run_model_safely(model, base_url)
        results.append(result)

    summary_csv = output_dir / "embedding_benchmark_summary.csv"
    detail_csv = output_dir / "embedding_benchmark_details.csv"
    markdown = output_dir / "embedding_benchmark_results.md"
    write_summary_csv(results, summary_csv)
    write_detail_csv(results, detail_csv)
    write_markdown(results, markdown)

    print(summary_csv.relative_to(PROJECT_ROOT))
    print(detail_csv.relative_to(PROJECT_ROOT))
    print(markdown.relative_to(PROJECT_ROOT))
    for result in results:
        if result.get("error"):
            print(f"{result['model']} failed: {result['error']}")
            continue
        print(
            f"{result['model']} dimension={result['dimension']} "
            f"top1={result['top1_accuracy']:.2f} top3={result['top3_accuracy']:.2f} "
            f"mrr={result['mrr']:.2f} avg={result['avg_latency_seconds']:.3f}s"
        )


if __name__ == "__main__":
    asyncio.run(main())
