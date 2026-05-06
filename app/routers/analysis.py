import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.analysis import AnalysisRequest
from app.agent.graph import agent_graph
from app.agent.state import AgentState
from app.models.report import ReportORM
from app.models.sales import SalesRecordORM, SalesUploadORM
from app.models.user import StoreSetupRequest

router = APIRouter()


@router.post("/setup")
async def setup_store(data: StoreSetupRequest, db: AsyncSession = Depends(get_db)):
    """사용자 로그인 및 가게 위치 정보 저장"""
    from app.models.user import StoreORM
    store = StoreORM(
        user_id=uuid.UUID(data.user_id) if "-" in data.user_id else uuid.uuid4(),
        name=data.store_name,
        district=data.location.district,
        station=data.location.station,
        latitude=data.location.latitude,
        longitude=data.location.longitude,
    )
    db.add(store)
    await db.commit()
    await db.refresh(store)
    return {"store_id": str(store.id), "message": "가게 정보가 저장되었습니다."}


@router.post("/analyze", response_model=dict)
async def analyze(
    request: AnalysisRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """분석 요청 — 리포트를 생성하고 에이전트 그래프를 백그라운드에서 실행합니다."""
    if request.date_range and request.date_range.start > request.date_range.end:
        raise HTTPException(status_code=400, detail="date_range.start는 end보다 늦을 수 없습니다.")

    store_location = await _get_store_location(db, request.store_id)
    upload_info = await _get_upload_info(db, request.store_id, request.file_id)

    report_record = ReportORM(
        store_id=request.store_id,
        mode=request.mode,
        user_query=request.query,
        status="processing",
    )
    db.add(report_record)
    await db.commit()
    await db.refresh(report_record)

    initial_state = _build_initial_state(request, store_location, upload_info)

    background_tasks.add_task(_run_agent, initial_state, report_record.report_id)

    return {"report_id": str(report_record.report_id), "status": "processing"}


async def _get_store_location(db: AsyncSession, store_id: uuid.UUID) -> dict[str, Any]:
    from app.models.user import StoreORM

    result = await db.execute(select(StoreORM).where(StoreORM.id == store_id))
    store = result.scalar_one_or_none()
    if not store:
        raise HTTPException(status_code=404, detail="가게 정보를 찾을 수 없습니다.")

    return {
        "district": store.district,
        "station": store.station,
        "lat": store.latitude,
        "lng": store.longitude,
    }


async def _get_upload_info(
    db: AsyncSession,
    store_id: uuid.UUID,
    file_id: uuid.UUID | None,
) -> dict[str, Any]:
    if not file_id:
        return {"file_path": None, "sales_date_range": None}

    result = await db.execute(
        select(SalesUploadORM).where(SalesUploadORM.sales_upload_id == file_id)
    )
    upload = result.scalar_one_or_none()
    if not upload:
        raise HTTPException(status_code=404, detail="업로드 파일을 찾을 수 없습니다.")
    if upload.store_id != store_id:
        raise HTTPException(status_code=403, detail="해당 가게의 업로드 파일이 아닙니다.")
    if upload.status != "done":
        raise HTTPException(status_code=409, detail="아직 처리 완료되지 않은 업로드 파일입니다.")

    range_result = await db.execute(
        select(
            func.min(SalesRecordORM.sales_date),
            func.max(SalesRecordORM.sales_date),
        ).where(SalesRecordORM.upload_id == file_id)
    )
    start_date, end_date = range_result.one()
    sales_date_range = None
    if start_date and end_date:
        sales_date_range = {
            "start": str(start_date),
            "end": str(end_date),
            "source": "uploaded_sales",
        }

    return {"file_path": upload.file_path, "sales_date_range": sales_date_range}


def _build_initial_state(
    request: AnalysisRequest,
    store_location: dict[str, Any],
    upload_info: dict[str, Any],
) -> AgentState:
    request_date_range = {
        "start": str(request.date_range.start),
        "end": str(request.date_range.end),
        "source": "request",
    } if request.date_range else None
    resolved_date_range = request_date_range or upload_info.get("sales_date_range")

    return {
        "user_query": request.query,
        "store_id": str(request.store_id),
        "store_location": store_location,
        "uploaded_file_path": upload_info.get("file_path"),
        "mode": request.mode,
        "date_range": resolved_date_range,
        "hypotheses": [],
        "analysis_plan": [],
        "tool_calls": [],
        "internal_data": None,
        "external_data": None,
        "estimated_data": None,
        "rag_context": None,
        "correlation_results": None,
        "statistical_summary": None,
        "final_report_json": None,
        "chart_data": None,
        "retry_count": 0,
        "is_sufficient": False,
    }


async def _run_agent(state: AgentState, report_id: uuid.UUID):
    import traceback

    from app.db.database import AsyncSessionLocal

    try:
        final_state = await agent_graph.ainvoke(state)
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(ReportORM).where(ReportORM.report_id == report_id))
            report = result.scalar_one_or_none()
            if not report:
                return

            report.status = "completed"
            report.report_data = _normalize_report_data(final_state.get("final_report_json"))
            report.chart_data = final_state.get("chart_data") or _build_chart_data(final_state)

            estimated = final_state.get("estimated_data") or {}
            report.interpolated_fields = list(estimated.keys())
            report.realtime_available = str(len(estimated) == 0).lower()
            report.confidence_level = _infer_confidence_level(estimated)
            report.completed_at = datetime.utcnow()
            await db.commit()
    except Exception as e:
        print(f"Agent Execution Failed for {report_id}: {e}")
        traceback.print_exc()
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(ReportORM).where(ReportORM.report_id == report_id))
            report = result.scalar_one_or_none()
            if report:
                report.status = "failed"
                report.report_data = {
                    "summary": "분석 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.",
                    "analysis_details": [
                        {
                            "factor": "agent_execution",
                            "impact": "중립",
                            "description": str(e),
                        }
                    ],
                    "action_items": ["업로드 파일과 날짜 범위를 확인한 뒤 다시 분석을 요청해 주세요."],
                }
                report.completed_at = datetime.utcnow()
                await db.commit()


def _normalize_report_data(report_data: Any) -> dict[str, Any]:
    if not isinstance(report_data, dict):
        return {
            "summary": "분석은 완료되었지만 리포트 형식 변환에 실패했습니다.",
            "analysis_details": [],
            "action_items": [],
        }

    return {
        "summary": report_data.get("summary") or "분석이 완료되었습니다.",
        "analysis_details": report_data.get("analysis_details") or [],
        "action_items": report_data.get("action_items") or [],
    }


def _build_chart_data(final_state: AgentState) -> dict[str, Any] | None:
    internal = final_state.get("internal_data") or {}
    time_series = internal.get("time_series")
    if not isinstance(time_series, list) or not time_series:
        return None

    categories: list[str] = []
    values: list[float] = []

    for index, item in enumerate(time_series):
        if isinstance(item, dict):
            label = item.get("date") or item.get("label") or item.get("period") or str(index + 1)
            value = item.get("amount") or item.get("sales") or item.get("value")
        else:
            label = str(index + 1)
            value = item

        try:
            values.append(float(value))
            categories.append(str(label))
        except (TypeError, ValueError):
            continue

    if not values:
        return None

    return {
        "type": "line",
        "categories": categories,
        "series": [{"name": "매출", "data": values}],
    }


def _infer_confidence_level(estimated: dict[str, Any]) -> str:
    if not estimated:
        return "high"

    confidences = [
        value.get("confidence")
        for value in estimated.values()
        if isinstance(value, dict) and value.get("confidence")
    ]
    if "low" in confidences:
        return "low"
    if "medium" in confidences:
        return "medium"
    return "medium"
