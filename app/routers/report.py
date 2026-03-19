import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.report import ReportORM, ReportSummary, Report, DataQuality, ReportData, ChartData

router = APIRouter()


def _orm_to_report(r: ReportORM) -> Report:
    report_data = None
    if r.report_data:
        report_data = ReportData(**r.report_data)

    chart_data = None
    if r.chart_data:
        chart_data = ChartData(**r.chart_data)

    return Report(
        report_id=r.id,
        status=r.status,
        mode=r.mode,
        data_quality=DataQuality(
            realtime_available=r.realtime_available == "true",
            interpolated_fields=r.interpolated_fields or [],
            confidence=r.confidence_level or "medium",
        ),
        report_data=report_data,
        chart_data=chart_data,
        created_at=r.created_at,
    )


@router.get("/reports/{report_id}", response_model=Report)
async def get_report(report_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ReportORM).where(ReportORM.id == report_id))
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="리포트를 찾을 수 없습니다.")
    return _orm_to_report(report)


@router.get("/reports/store/{store_id}", response_model=List[ReportSummary])
async def list_reports(store_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ReportORM)
        .where(ReportORM.store_id == store_id)
        .order_by(ReportORM.created_at.desc())
        .limit(20)
    )
    reports = result.scalars().all()
    return [
        ReportSummary(
            report_id=r.id,
            mode=r.mode,
            user_query=r.user_query,
            status=r.status,
            confidence=r.confidence_level or "medium",
            created_at=r.created_at,
        )
        for r in reports
    ]
