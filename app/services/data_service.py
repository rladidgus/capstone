"""
매출 데이터 CRUD 서비스
"""
import uuid
from datetime import date
from typing import Optional

import pandas as pd
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sales import SalesRecordORM, SalesUploadORM, SalesSummary
from app.config import settings


class DataService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_upload(self, store_id: uuid.UUID, file_name: str, file_path: str) -> SalesUploadORM:
        upload = SalesUploadORM(
            store_id=store_id,
            file_name=file_name,
            file_path=file_path,
            status="pending",
        )
        self.db.add(upload)
        await self.db.commit()
        await self.db.refresh(upload)
        return upload

    async def process_csv(self, upload: SalesUploadORM) -> int:
        """CSV를 파싱하여 SalesRecord 레코드로 저장합니다."""
        df = pd.read_csv(upload.file_path)
        # 필수 컬럼 매핑 (파일 포맷에 따라 조정 필요)
        records = []
        for _, row in df.iterrows():
            records.append(SalesRecordORM(
                store_id=upload.store_id,
                upload_id=upload.id,
                sold_at=pd.to_datetime(row.get("sold_at") or row.get("일시")),
                sales_date=pd.to_datetime(row.get("sold_at") or row.get("일시")).date(),
                amount=float(row.get("amount") or row.get("매출액", 0)),
                menu_name=row.get("menu") or row.get("메뉴"),
                category=row.get("category") or row.get("카테고리"),
            ))
        self.db.add_all(records)
        upload.status = "done"
        upload.row_count = len(records)
        await self.db.commit()
        return len(records)

    async def get_sales_summary(
        self,
        store_id: uuid.UUID,
        start: date,
        end: date,
    ) -> Optional[SalesSummary]:
        stmt = select(SalesRecordORM).where(
            and_(
                SalesRecordORM.store_id == store_id,
                SalesRecordORM.sales_date >= start,
                SalesRecordORM.sales_date <= end,
            )
        )
        result = await self.db.execute(stmt)
        records = result.scalars().all()
        if not records:
            return None

        df = pd.DataFrame([
            {"date": r.sales_date, "amount": float(r.amount), "hour": r.hour,
             "day": r.day_of_week, "menu": r.menu_name}
            for r in records
        ])

        time_series = (
            df.groupby("date")["amount"].sum()
            .reset_index()
            .rename(columns={"date": "date", "amount": "amount"})
            .to_dict("records")
        )
        top_menus = (
            df.groupby("menu")["amount"].sum()
            .nlargest(5)
            .reset_index()
            .to_dict("records")
        ) if "menu" in df.columns else []

        return SalesSummary(
            store_id=store_id,
            period_start=start,
            period_end=end,
            total_amount=df["amount"].sum(),
            avg_daily_amount=df.groupby("date")["amount"].sum().mean(),
            peak_hour=int(df.groupby("hour")["amount"].sum().idxmax()) if "hour" in df.columns else None,
            top_menus=top_menus,
            time_series=time_series,
        )
