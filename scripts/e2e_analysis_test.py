"""
분석 E2E 검증 스크립트.

실행 범위:
1. 테스트 가게 생성/재사용
2. 테스트 매출 CSV 생성
3. DataService 업로드 처리
4. /analysis/analyze와 동일한 초기 상태 구성
5. 에이전트 실행 후 ReportORM 저장 확인

사용:
    python scripts/e2e_analysis_test.py
"""
import argparse
import asyncio
import csv
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

load_dotenv(".env")

from app.db.database import AsyncSessionLocal, init_db
from app.models.analysis import AnalysisRequest
from app.models.report import ReportORM
from app.models.user import StoreORM, UserORM
from app.routers.analysis import _build_initial_state, _get_store_location, _get_upload_info, _run_agent
from app.services.data_service import DataService


E2E_USER_ID = uuid.uuid5(uuid.NAMESPACE_DNS, "viewpoint-e2e-user")
E2E_EMAIL = "viewpoint-e2e@example.com"
E2E_STORE_NAME = "E2E 홍대 테스트 매장"


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
                quantity = 2 if hour in (12, 13) else 1
                amount = int(base_amount * quantity * weekday_boost)
                rows.append(
                    {
                        "sold_at": datetime.combine(sales_date, datetime.min.time()).replace(hour=hour).isoformat(),
                        "amount": amount,
                        "quantity": quantity,
                        "menu": menu_name,
                        "category": category,
                    }
                )

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["sold_at", "amount", "quantity", "menu", "category"])
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
                hashed_password="e2e_dummy_password",
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


async def run(query: str, mode: str) -> int:
    await init_db()

    store = await _get_or_create_store()
    upload_dir = Path(os.getenv("UPLOAD_DIR", "data/uploads"))
    csv_path = upload_dir / f"e2e_analysis_{uuid.uuid4()}.csv"
    _write_sales_csv(csv_path)

    upload, row_count = await _create_sales_upload(store.id, csv_path)
    report_id, state = await _create_report_and_state(store.id, upload.sales_upload_id, query, mode)

    print(f"store_id={store.id}")
    print(f"upload_id={upload.sales_upload_id} row_count={row_count}")
    print(f"report_id={report_id}")
    print(f"date_range={state.get('date_range')}")
    print("agent_status=running")

    await _run_agent(state, report_id)

    report = await _load_report(report_id)
    if not report:
        print("E2E_FAIL: report not found")
        return 1

    print(f"agent_status={report.status}")
    print(f"completed_at={report.completed_at}")
    print(f"has_report_data={bool(report.report_data)}")
    print(f"has_chart_data={bool(report.chart_data)}")
    print(f"interpolated_fields={report.interpolated_fields}")
    print(f"confidence_level={report.confidence_level}")

    if report.status != "completed":
        print(f"E2E_FAIL: report status is {report.status}")
        print(f"report_data={report.report_data}")
        return 1

    if not report.report_data:
        print("E2E_FAIL: report_data is empty")
        return 1

    print("E2E_OK")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run analysis E2E test.")
    parser.add_argument(
        "--query",
        default="최근 일주일 매출 변동 원인을 외부 요인과 함께 요약해줘",
    )
    parser.add_argument("--mode", choices=["quick", "deep"], default="quick")
    args = parser.parse_args()

    return asyncio.run(run(query=args.query, mode=args.mode))


if __name__ == "__main__":
    raise SystemExit(main())
