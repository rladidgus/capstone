import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.memo import Memo, MemoCreate, MemoUpdate
from app.services.memo_service import MemoService

from app.routers.auth import get_current_store

router = APIRouter()


@router.get("/", response_model=List[Memo])
async def list_memos(db: AsyncSession = Depends(get_db), store_id: uuid.UUID = Depends(get_current_store)):
    service = MemoService(db)
    memos = await service.list_memos(store_id)
    return memos


@router.post("/", response_model=Memo, status_code=201)
async def create_memo(data: MemoCreate, db: AsyncSession = Depends(get_db), store_id: uuid.UUID = Depends(get_current_store)):
    data.store_id = store_id
    service = MemoService(db)
    memo = await service.create_memo(data)
    return memo


@router.patch("/{memo_id}", response_model=Memo)
async def update_memo(memo_id: uuid.UUID, data: MemoUpdate, db: AsyncSession = Depends(get_db), store_id: uuid.UUID = Depends(get_current_store)):
    service = MemoService(db)
    memo = await service.update_memo(memo_id, store_id, data)
    if not memo:
        raise HTTPException(status_code=404, detail="메모를 찾을 수 없습니다.")
    return memo


@router.delete("/{memo_id}", status_code=204)
async def delete_memo(memo_id: uuid.UUID, db: AsyncSession = Depends(get_db), store_id: uuid.UUID = Depends(get_current_store)):
    service = MemoService(db)
    await service.delete_memo(memo_id, store_id)
