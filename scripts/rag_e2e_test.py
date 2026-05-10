"""RAG E2E test with the selected embedding model.

Flow:
1. Create/reuse E2E store.
2. Create a memo through MemoService.
3. Verify embedding upsert/search in Pinecone.
4. Run analysis E2E.
5. Verify the final report reflects memo/RAG context.
"""
import argparse
import asyncio
import csv
import json
import os
import sys
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import select

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv(PROJECT_ROOT / ".env")

from app.db.database import AsyncSessionLocal, init_db
from app.db.vector_store import get_pinecone_index
from app.models.analysis import AnalysisRequest
from app.models.memo import MemoCreate, MemoORM
from app.models.report import ReportORM
from app.models.user import StoreORM, UserORM
from app.routers.analysis import _build_initial_state, _get_store_location, _get_upload_info, _run_agent
from app.services.data_service import DataService
from app.services.llm_service import LLMService
from app.services.memo_service import MemoService


E2E_USER_ID = uuid.uuid5(uuid.NAMESPACE_DNS, "viewpoint-rag-e2e-user")
E2E_EMAIL = "viewpoint-rag-e2e@example.com"
E2E_STORE_NAME = "RAG E2E 홍대 테스트 매장"
MEMO_MARKER = "RAG_E2E_LATTE_RAIN"


def _write_sales_csv(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    today = date.today()
    rows = []
    menus = [
        ("아메리카노", "음료", 4500),
        ("라떼", "음료", 5200),
        ("샌드위치", "푸드", 7800),
    ]

    for day_offset in range(6, -1, -1):
        sales_date = today - timedelta(days=day_offset)
        weekday_boost = 1.15 if sales_date.weekday() < 5 else 0.9
        for hour in (11, 12, 13, 18):
            for menu_name, category, base_amount in menus:
                quantity = 3 if menu_name == "라떼" and hour == 12 else 1
                amount = int(base_amount * quantity * weekday_boost)
                rows.append({
                    "sold_at": datetime.combine(sales_date, datetime.min.time()).replace(hour=hour).isoformat(),
                    "amount": amount,
                    "quantity": quantity,
                    "menu": menu_name,
                    "category": category,
                })

    with path.open("w", newline="", encoding="utf-8") as fp:
        writer = csv.DictWriter(fp, fieldnames=["sold_at", "amount", "quantity", "menu", "category"])
        writer.writeheader()
        writer.writerows(rows)


async def _get_or_create_store() -> StoreORM:
    async with AsyncSessionLocal() as db:
        user_result = await db.execute(select(UserORM).where(UserORM.user_id == E2E_USER_ID))
        user = user_result.scalar_one_or_none()
        if not user:
            user = UserORM(
                user_id=E2E_USER_ID,
                email=E2E_EMAIL,
                hashed_password="rag_e2e_dummy_password",
            )
            db.add(user)
            await db.commit()

        store_result = await db.execute(
            select(StoreORM)
            .where(StoreORM.user_id == E2E_USER_ID)
            .where(StoreORM.name == E2E_STORE_NAME)
        )
        store = store_result.scalar_one_or_none()
        if store:
            return store

        store = StoreORM(
            user_id=E2E_USER_ID,
            name=E2E_STORE_NAME,
            district="마포구",
            station="홍대입구역",
            latitude=37.557192,
            longitude=126.925381,
        )
        db.add(store)
        await db.commit()
        await db.refresh(store)
        return store


async def _create_memo(store_id: uuid.UUID) -> MemoORM:
    async with AsyncSessionLocal() as db:
        service = MemoService(db)
        memo = await service.create_memo(
            MemoCreate(
                store_id=store_id,
                memo_date=date.today(),
                title="비 오는 날 라떼 준비량 메모",
                content=(
                    f"{MEMO_MARKER}: 비 오는 날에는 따뜻한 라떼 준비량을 30% 늘렸을 때 "
                    "오후 매출과 고객 반응이 좋아졌다."
                ),
                tags=["날씨", "라떼", "RAG_E2E"],
            )
        )
        await db.refresh(memo)
        return memo


async def _verify_pinecone_search(store_id: uuid.UUID, memo: MemoORM) -> tuple[bool, str]:
    llm = LLMService()
    query_vector = await llm.embed("비 오는 날 라떼 준비량을 늘린 메모를 찾아줘")
    index = get_pinecone_index()

    for attempt in range(1, 6):
        results = index.query(
            vector=query_vector,
            top_k=5,
            include_metadata=True,
            filter={"store_id": str(store_id)},
        )
        matches = results.get("matches", [])
        for match in matches:
            metadata = match.get("metadata") or {}
            if metadata.get("memo_id") == str(memo.memo_id) or MEMO_MARKER in metadata.get("content", ""):
                return True, f"found attempt={attempt} score={match.get('score')}"
        await asyncio.sleep(1)

    return False, f"not found memo_id={memo.memo_id}"


async def _create_sales_upload(store_id: uuid.UUID, file_path: Path):
    async with AsyncSessionLocal() as db:
        service = DataService(db)
        upload = await service.create_upload(store_id, file_path.name, str(file_path))
        row_count = await service.process_csv(upload)
        await db.refresh(upload)
        return upload, row_count


async def _create_report_and_state(store_id: uuid.UUID, upload_id: uuid.UUID, query: str, mode: str):
    async with AsyncSessionLocal() as db:
        request = AnalysisRequest(
            query=query,
            mode=mode,
            store_id=store_id,
            file_id=upload_id,
        )
        store_location = await _get_store_location(db, request.store_id)
        upload_info = await _get_upload_info(db, request.store_id, request.file_id)

        report = ReportORM(
            store_id=request.store_id,
            mode=request.mode,
            user_query=request.query,
            status="processing",
        )
        db.add(report)
        await db.commit()
        await db.refresh(report)

        state = _build_initial_state(request, store_location, upload_info)
        return report.report_id, state


async def _load_report(report_id: uuid.UUID) -> ReportORM | None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(ReportORM).where(ReportORM.report_id == report_id))
        return result.scalar_one_or_none()


def _report_contains_rag(report: ReportORM) -> bool:
    payload = json.dumps(report.report_data or {}, ensure_ascii=False)
    return MEMO_MARKER in payload or ("라떼" in payload and "메모" in payload)


async def run(mode: str) -> int:
    await init_db()
    print(f"embed_model={os.getenv('OLLAMA_EMBED_MODEL')}")

    store = await _get_or_create_store()
    memo = await _create_memo(store.id)
    print(f"memo_id={memo.memo_id}")
    print(f"memo_is_embedded={memo.is_embedded}")
    print(f"memo_vector_id={memo.vector_id}")

    if memo.is_embedded != "done":
        print("RAG_E2E_FAIL: memo embedding failed")
        return 1

    found, search_message = await _verify_pinecone_search(store.id, memo)
    print(f"pinecone_search={search_message}")
    if not found:
        print("RAG_E2E_FAIL: memo not found in Pinecone search")
        return 1

    upload_dir = Path(os.getenv("UPLOAD_DIR", "data/uploads"))
    csv_path = upload_dir / f"rag_e2e_analysis_{uuid.uuid4()}.csv"
    _write_sales_csv(csv_path)
    upload, row_count = await _create_sales_upload(store.id, csv_path)
    print(f"upload_id={upload.sales_upload_id} row_count={row_count}")

    query = "최근 일주일 매출 변동을 경영 메모까지 반영해서 요약해줘. 비 오는 날 라떼 준비량 메모가 있으면 반드시 반영해줘."
    report_id, state = await _create_report_and_state(store.id, upload.sales_upload_id, query, mode)
    print(f"report_id={report_id}")
    print(f"date_range={state.get('date_range')}")
    print("agent_status=running")

    await _run_agent(state, report_id)
    report = await _load_report(report_id)
    if not report:
        print("RAG_E2E_FAIL: report not found")
        return 1

    print(f"agent_status={report.status}")
    print(f"has_report_data={bool(report.report_data)}")
    print(f"has_chart_data={bool(report.chart_data)}")
    print(f"confidence_level={report.confidence_level}")
    print(f"report_contains_rag={_report_contains_rag(report)}")

    if report.status != "completed":
        print(f"RAG_E2E_FAIL: report status is {report.status}")
        print(f"report_data={report.report_data}")
        return 1
    if not _report_contains_rag(report):
        print("RAG_E2E_FAIL: report did not include memo/RAG context")
        print(f"report_data={report.report_data}")
        return 1

    print("RAG_E2E_OK")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run memo/RAG E2E test.")
    parser.add_argument("--mode", choices=["quick", "deep"], default="quick")
    args = parser.parse_args()
    return asyncio.run(run(args.mode))


if __name__ == "__main__":
    raise SystemExit(main())
