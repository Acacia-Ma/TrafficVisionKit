"""FastAPI 应用入口（Phase 2：所有 REST + WebSocket 路由已挂载）。"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.config import get_settings
from routers import (
    auth_router,
    devices_router,
    history_router,
    system_router,
    users_router,
    ws_router,
)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：Phase 3+ 会在此处启动 TCP Server 和 PipelineManager。"""
    yield


app = FastAPI(
    title="车辆检测与计数系统",
    description="STM32 采集 → TCP 传输 → YOLO 推理 → WebSocket 推送",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 路由挂载 ─────────────────────────────────────────────────────────────────────
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(devices_router)
app.include_router(history_router)
app.include_router(system_router)
app.include_router(ws_router)


@app.get("/api/health", tags=["system"])
async def health_check():
    """快速健康检查（无需鉴权）。"""
    return {"status": "ok", "version": "0.2.0"}
