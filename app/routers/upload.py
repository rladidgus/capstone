import os
import uuid
import shutil

from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.services.data_service import DataService

from app.routers.auth import get_current_store
from sqlalchemy import select, delete
from app.models.sales import SalesUploadORM, SalesRecordORM

router = APIRouter()


@router.post("/")
async def upload_sales_file(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    store_id: uuid.UUID = Depends(get_current_store),
):
    """매출 CSV/XLSX 파일 업로드"""
    allowed_types = {"text/csv", "application/vnd.ms-excel",
                     "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}
    if file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail="CSV 또는 XLSX 파일만 업로드 가능합니다.")

    upload_dir = os.getenv("UPLOAD_DIR", "data/uploads")
    os.makedirs(upload_dir, exist_ok=True)
    file_path = os.path.join(upload_dir, f"{uuid.uuid4()}_{file.filename}")

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    service = DataService(db)
    upload = await service.create_upload(store_id, file.filename, file_path)
    row_count = await service.process_csv(upload)

    return {
        "file_id": str(upload.sales_upload_id),
        "file_name": file.filename,
        "row_count": row_count,
        "status": "done",
    }


@router.get("/list")
async def list_uploads(
    db: AsyncSession = Depends(get_db),
    store_id: uuid.UUID = Depends(get_current_store),
):
    """업로드된 파일 목록 조회"""
    result = await db.execute(
        select(SalesUploadORM)
        .where(SalesUploadORM.store_id == store_id)
        .order_by(SalesUploadORM.uploaded_at.desc())
    )
    uploads = result.scalars().all()
    return [
        {
            "file_id": str(u.sales_upload_id),
            "file_name": u.file_name,
            "row_count": u.row_count,
            "status": u.status,
            "uploaded_at": u.uploaded_at
        }
        for u in uploads
    ]


@router.delete("/{file_id}", status_code=204)
async def delete_upload(
    file_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    store_id: uuid.UUID = Depends(get_current_store),
):
    """특정 파일 삭제"""
    result = await db.execute(select(SalesUploadORM).where(SalesUploadORM.sales_upload_id == file_id))
    upload = result.scalar_one_or_none()
    
    if not upload:
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다.")
    if upload.store_id != store_id:
        raise HTTPException(status_code=403, detail="삭제 권한이 없습니다.")
    
    # 1. 연관된 매출 레코드 삭제
    await db.execute(delete(SalesRecordORM).where(SalesRecordORM.upload_id == file_id))
    
    # 2. 업로드 레코드 삭제
    await db.delete(upload)
    await db.commit()
    
    # 3. 파일 물리적 삭제
    if os.path.exists(upload.file_path):
        try:
            os.remove(upload.file_path)
        except OSError:
            pass
    
    return
