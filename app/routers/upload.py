import os
import uuid
import shutil

from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.services.data_service import DataService
from app.config import settings

router = APIRouter()


@router.post("/upload")
async def upload_sales_file(
    store_id: uuid.UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """매출 CSV/XLSX 파일 업로드"""
    allowed_types = {"text/csv", "application/vnd.ms-excel",
                     "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}
    if file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail="CSV 또는 XLSX 파일만 업로드 가능합니다.")

    os.makedirs(settings.upload_dir, exist_ok=True)
    file_path = os.path.join(settings.upload_dir, f"{uuid.uuid4()}_{file.filename}")

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    service = DataService(db)
    upload = await service.create_upload(store_id, file.filename, file_path)
    row_count = await service.process_csv(upload)

    return {
        "file_id": str(upload.id),
        "file_name": file.filename,
        "row_count": row_count,
        "status": "done",
    }
