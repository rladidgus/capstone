import uuid
from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.analysis import AnalysisRequest
from app.models.report import Report
from app.agent.graph import agent_graph
from app.agent.state import AgentState
from app.models.report import ReportORM
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
    """분석 요청 — 에이전트 그래프를 실행합니다."""
    report_record = ReportORM(
        store_id=request.store_id,
        mode=request.mode,
        user_query=request.query,
        status="processing",
    )
    db.add(report_record)
    await db.commit()
    await db.refresh(report_record)

    file_path = None
    if request.file_id:
        from sqlalchemy import select
        from app.models.sales import SalesUploadORM
        res = await db.execute(select(SalesUploadORM).where(SalesUploadORM.sales_upload_id == request.file_id))
        upload_record = res.scalars().first()
        if upload_record:
            file_path = upload_record.file_path

    initial_state: AgentState = {
        "user_query": request.query,
        "store_id": str(request.store_id),
        "uploaded_file_path": file_path,
        "mode": request.mode,
        "date_range": {
            "start": str(request.date_range.start),
            "end": str(request.date_range.end),
        } if request.date_range else None,
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

    background_tasks.add_task(_run_agent, initial_state, report_record.report_id)

    return {"report_id": str(report_record.report_id), "status": "processing"}


async def _run_agent(state: AgentState, report_id: uuid.UUID):
    import traceback
    from datetime import datetime
    from sqlalchemy import select
    from app.db.database import AsyncSessionLocal

    try:
        final_state = await agent_graph.ainvoke(state)
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(ReportORM).where(ReportORM.report_id == report_id))
            report = result.scalar_one()
            report.status = "completed"
            report.report_data = final_state.get("final_report_json")
            report.chart_data = final_state.get("chart_data")

            estimated = final_state.get("estimated_data") or {}
            report.interpolated_fields = list(estimated.keys())
            report.realtime_available = str(len(estimated) == 0).lower()
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
                await db.commit()
