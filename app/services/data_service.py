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
        """CSV/XLSX를 파싱하여 SalesRecord 레코드로 저장합니다."""
        
        # 파일 확장자에 따라 pandas 읽기 방식 분기
        file_ext = upload.file_path.split('.')[-1].lower()
        if file_ext in ['xlsx', 'xls']:
            df = pd.read_excel(upload.file_path)
        else:
            try:
                # 1차 시도: 일반적인 utf-8
                df = pd.read_csv(upload.file_path, encoding='utf-8')
            except UnicodeDecodeError:
                # 2차 시도: 한글 엑셀 데이터용 cp949
                df = pd.read_csv(upload.file_path, encoding='cp949')
        
        # 컬럼 이름 앞뒤 공백 제거 (안전망)
        df.columns = df.columns.astype(str).str.strip()
            
        records = []
        for _, row in df.iterrows():
            # 유연한 컬럼명 (헤더) 매핑
            # 모든 속성을 str()로 변환하고 양쪽 공백도 제거하여 정확한 매치 시도
            def get_val(*keys):
                for k in keys:
                    if k in df.columns:
                        return row[k]
                return None
                
            sold_at_val = get_val("sold_at", "일시", "결제일시", "기본판매일시", "판매일시", "날짜")
            amount_val = get_val("amount", "매출액", "결제금액", "합계금액", "총실매출금액") or 0
            qty_val = get_val("quantity", "수량", "판매수량") or 1
            
            # 시간 데이터가 없으면 패스 (빈 줄 무시)
            if pd.isna(sold_at_val) or str(sold_at_val).strip() == "":
                continue
            if pd.isna(sold_at_val) or sold_at_val is None:
                continue
                
            dt = pd.to_datetime(sold_at_val)
            
            records.append(SalesRecordORM(
                store_id=upload.store_id,
                upload_id=upload.sales_upload_id,  # 중요: 모델 PK 이름 매칭
                sold_at=dt,
                sales_date=dt.date(),
                hour=dt.hour,
                day_of_week=dt.weekday(),
                amount=float(amount_val),
                quantity=int(qty_val),
                menu_name=str(get_val("menu", "메뉴", "상품명") or "알수없음"),
                category=str(get_val("category", "카테고리", "대분류명") or "기타"),
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
