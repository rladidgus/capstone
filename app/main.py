import os
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import analysis, upload, memo, report, auth, dashboard
from app.db.database import init_db

app = FastAPI(
    title="ViewPoint API",
    description="소상공인을 위한 자율형 경영 분석 AI 에이전트",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(analysis.router, prefix="/analysis", tags=["analysis"])
app.include_router(upload.router, prefix="/upload", tags=["upload"])
app.include_router(memo.router, prefix="/memo", tags=["memo"])
app.include_router(report.router, prefix="/report", tags=["report"])
app.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])


@app.on_event("startup")
async def startup():
    await init_db()


@app.get("/health")
async def health_check():
    return {"status": "ok"}
