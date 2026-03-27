from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.db.supabase_client import supabase
from app.db.database import get_db

router = APIRouter()
security = HTTPBearer()

@router.get("/login/google", summary="Google 로그인 시작 (OAuth)")
async def login_google(request: Request):
    """
    Supabase를 이용해 Google 소셜 로그인을 시작합니다.
    클라이언트를 구글 로그인 페이지로 리디렉션합니다.
    """
    # 콜백 URL 지정 (로컬 환경 예시)
    redirect_url = str(request.url_for("auth_callback"))
    
    res = supabase.auth.sign_in_with_oauth({
        "provider": "google",
        "options": {
            "redirect_to": redirect_url
        }
    })
    
    if hasattr(res, 'url'):
        return RedirectResponse(url=res.url)
    
    raise HTTPException(status_code=500, detail="소셜 로그인 초기화 실패")

@router.get("/google/callback", summary="로그인 콜백")
async def auth_callback(request: Request, code: str = None):
    """
    구글 로그인 이후 리디렉션 되는 엔드포인트입니다.
    URL 쿼리에 있는 'code'를 실제 JWT(Access Token)로 교환합니다.
    """
    if code:
        try:
            # 전달받은 일회성 코드를 진짜 JWT(Access Token)로 교환
            session_info = supabase.auth.exchange_code_for_session({"auth_code": code})
            
            # 발급받은 JWT 및 세션 정보 확인
            access_token = session_info.session.access_token
            return {
                "message": "로그인 및 토큰 발급 성공!",
                "access_token": access_token,
                "instruction": "위의 access_token(매우 긴 문자열)을 복사해서 /auth/me 테스트 시 Authorization 헤더(Bearer) 값으로 사용하세요!"
            }
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"토큰 발급 실패: {str(e)}")
            
    return {
        "message": "code 파라미터가 없습니다. URL 해시(#access_token=...) 형태로 토큰이 전달되었는지 주소창을 확인하세요."
    }

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """
    Authorization Bearer 토큰(Supabase JWT)을 검증하여 사용자 정보를 반환하는 의존성 함수입니다.
    보호된 엔드포인트에 사용할 수 있습니다.
    """
    token = credentials.credentials
    try:
        # Supabase를 통해 토큰 검증 및 유저 정보 확인
        user_response = supabase.auth.get_user(token)
        if not user_response.user:
            raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다.")
        return user_response.user
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))

@router.get("/me", summary="내 정보 확인")
async def get_me(user = Depends(get_current_user)):
    """
    현재 로그인된 사용자의 정보를 반환합니다.
    """
    return user


async def get_current_store(
    user = Depends(get_current_user),
    db = Depends(get_db)
):
    """
    JWT 토큰으로 로그인된 유저의 등록된 첫 번째 가게(Store) ID를 조회하여 반환합니다.
    """
    from sqlalchemy import select
    from app.models.user import StoreORM
    import uuid
    
    try:
        user_uuid = uuid.UUID(user.id)
    except Exception:
        raise HTTPException(status_code=401, detail="유효하지 않은 유저 ID 포맷입니다.")
        
    result = await db.execute(select(StoreORM).where(StoreORM.user_id == user_uuid))
    store = result.scalars().first()
    if not store:
        raise HTTPException(status_code=403, detail="등록된 가게 정보가 없습니다.")
    return store.id

@router.post("/setup", summary="최초 가입 시 상점 정보 기본 설정 (온보딩)", response_model=__import__("app.models.user", fromlist=["StoreSetupResponse"]).StoreSetupResponse)
async def auth_setup(
    setup_data: __import__("app.models.user", fromlist=["StoreSetupRequest"]).StoreSetupRequest,
    db: __import__("sqlalchemy.ext.asyncio", fromlist=["AsyncSession"]).AsyncSession = Depends(get_db),
    user = Depends(get_current_user)
):
    """
    구글 로그인 이후, 최초 1회 상점(가게) 정보를 입력받아 DB에 저장하는 온보딩 라우터입니다.
    """
    from sqlalchemy.future import select
    from app.models.user import StoreORM, UserORM
    import uuid

    try:
        user_uuid = uuid.UUID(user.id)
    except Exception:
        raise HTTPException(status_code=401, detail="유효하지 않은 유저 ID 포맷입니다.")
    
    # 1. users 테이블에 현재 유저가 없다면(최초 로그인 시) 자동으로 생성해 줍니다.
    try:
        user_result = await db.execute(select(UserORM).where(UserORM.user_id == user_uuid))
        existing_user = user_result.scalars().first()
        if not existing_user:
            new_user = UserORM(
                user_id=user_uuid,
                email=getattr(user, "email", f"user_{user_uuid}@oauth.com"),
                hashed_password="oauth_dummy_password" # 소셜 로그인 전용 더미 비밀번호
            )
            db.add(new_user)
            await db.commit()
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"유저 정보 동기화 실패: {str(e)}")

    # 2. 이미 등록된 가게가 있는지 확인 (중복 등록 방지)
    store_result = await db.execute(select(StoreORM).where(StoreORM.user_id == user_uuid))
    if store_result.scalars().first():
        raise HTTPException(status_code=400, detail="이미 등록된 가게가 존재합니다. 대시보드로 이동하세요.")

    # 3. 새로운 상점(Store) 생성 및 저장
    new_store = StoreORM(
        user_id=user_uuid,
        name=setup_data.store_name,
        district=setup_data.location.district,
        station=setup_data.location.station,
        latitude=setup_data.location.latitude,
        longitude=setup_data.location.longitude,
    )
    
    db.add(new_store)
    try:
        await db.commit()
        await db.refresh(new_store)
        return {
            "message": "가게 설정(온보딩)이 완료되었습니다!", 
            "store_id": str(new_store.id),
            "store_name": new_store.name
        }
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"가게 정보 저장 실패: {str(e)}")
