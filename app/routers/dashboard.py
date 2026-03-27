import uuid
from datetime import date
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.db.database import get_db
from app.routers.auth import get_current_store
from app.models.sales import SalesRecordORM

router = APIRouter()

@router.get("/summary")
async def get_dashboard_summary(
    db: AsyncSession = Depends(get_db),
    store_id: uuid.UUID = Depends(get_current_store),
):
    """가장 최근의 유동인구, 전날 매출 요약 등을 가볍게 조회"""
    # 가장 최근 매출 일자 확인
    recent_date_result = await db.execute(
        select(func.max(SalesRecordORM.sales_date))
        .where(SalesRecordORM.store_id == store_id)
    )
    recent_date = recent_date_result.scalar_one_or_none()
    
    recent_sales = 0
    recent_count = 0
    
    if recent_date:
        # 1. 최근일 총 매출
        sales_result = await db.execute(
            select(func.sum(SalesRecordORM.amount))
            .where(SalesRecordORM.store_id == store_id)
            .where(SalesRecordORM.sales_date == recent_date)
        )
        recent_sales = sales_result.scalar_one_or_none() or 0
        
        # 2. 최근일 총 건수
        count_result = await db.execute(
            select(func.sum(SalesRecordORM.quantity))
            .where(SalesRecordORM.store_id == store_id)
            .where(SalesRecordORM.sales_date == recent_date)
        )
        recent_count = count_result.scalar_one_or_none() or 0
    
    # 유동인구 (Mock 데이터, 추후 외부 API 연동)
    recent_foot_traffic = 12500 
    
    return {
        "recent_date": recent_date,
        "recent_sales": float(recent_sales),
        "recent_count": int(recent_count),
        "recent_foot_traffic": recent_foot_traffic,
        "traffic_trend": "+5.2%",
    }
