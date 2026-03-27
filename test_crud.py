import os
import asyncio
from dotenv import load_dotenv

load_dotenv()

from sqlalchemy.future import select
from app.db.database import init_db, AsyncSessionLocal
from app.models.user import UserORM, StoreORM

async def run_crud_test():
    # 1. 테이블 생성 (필요 시 없으면 만듦)
    print("1️⃣ 데이터베이스 테이블 초기화 (또는 확인) 중...")
    await init_db()
    
    async with AsyncSessionLocal() as db:
        try:
            # ==========================================
            # [CREATE] 유저와 가게 생성
            # ==========================================
            print("\n2️⃣ [CREATE] 유저와 가게 데이터 생성 테스트")
            
            # 유저 생성 (중복 방지를 위해 email에 랜덤값 삽입이 필요할 수도 있지만, 테스트용 고정 이메일 사용 후 삭제)
            import uuid
            test_email = f"test_{uuid.uuid4().hex[:6]}@viewpoint.com"
            new_user = UserORM(
                email=test_email,
                hashed_password="fake_hashed_password"
            )
            db.add(new_user)
            await db.commit()
            await db.refresh(new_user)
            print(f"✅ 유저 생성 완료! (User ID: {new_user.user_id}, Email: {new_user.email})")
            
            # 방금 생성한 유저의 가게 생성
            new_store = StoreORM(
                user_id=new_user.user_id,
                name="마포구 뷰포인트 본점",
                district="마포구",
                station="합정역",
                latitude=37.549,
                longitude=126.913
            )
            db.add(new_store)
            await db.commit()
            await db.refresh(new_store)
            print(f"✅ 가게 생성 완료! (Store ID: {new_store.id}, Store Name: {new_store.name})")

            # ==========================================
            # [READ] 데이터 조회
            # ==========================================
            print("\n3️⃣ [READ] 데이터 조회 테스트")
            query = select(StoreORM).where(StoreORM.id == new_store.id)
            result = await db.execute(query)
            store_from_db = result.scalars().first()
            if store_from_db:
                print(f"✅ 조회 성공! 가져온 가게 이름: {store_from_db.name}")
            else:
                print("❌ 가게를 찾을 수 없습니다.")

            # ==========================================
            # [UPDATE] 데이터 수정
            # ==========================================
            print("\n4️⃣ [UPDATE] 데이터 수정 테스트 (가게 이름 변경)")
            store_from_db.name = "마포구 뷰포인트 본점 (임시 리뉴얼)"
            await db.commit()
            await db.refresh(store_from_db)
            print(f"✅ 수정 성공! 직접 확인한 변경된 이름: {store_from_db.name}")

            # ==========================================
            # [DELETE] 데이터 삭제
            # ==========================================
            print("\n5️⃣ [DELETE] 데이터 삭제 및 폭포수(Cascade) 확인 테스트")
            # UserORM에서 stores = relationship(..., cascade="all, delete-orphan") 설정이 되어 있으므로
            # 유저를 삭제하면 딸려있던 가게도 함께 삭제되어야 합니다.
            await db.delete(new_user)
            await db.commit()
            print(f"✅ 유저 삭제 완료 (User ID: {new_user.user_id})")
            
            # 연쇄 삭제 확인
            check_store_query = select(StoreORM).where(StoreORM.user_id == new_user.user_id)
            deleted_store_result = await db.execute(check_store_query)
            if deleted_store_result.scalars().first() is None:
                print("✅ 연결된 가게마저 데이터베이스에서 완벽하게 연쇄 삭제(Cascade) 처리되었습니다!")
            else:
                print("❌ 가게가 여전히 DB에 남아있습니다. 모델의 Cascade 설정을 확인해야 합니다.")

        except Exception as e:
            await db.rollback()
            print(f"❌ 오류 발생! 롤백 완료 (데이터 안전): {e}")

if __name__ == "__main__":
    asyncio.run(run_crud_test())
