"""FastAPI 应用入口（Phase 3：TCP Server + Pipeline 已整合到 lifespan）。"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.config import get_settings
from inference.engine import engine
from pipeline.manager import pipeline_manager
from routers import (
    auth_router,
    devices_router,
    history_router,
    system_router,
    users_router,
    ws_router,
)
from tcp.server import TCPServer

logger = logging.getLogger(__name__)
settings = get_settings()

# TCP Server 单例
_tcp_server = TCPServer(host=settings.TCP_HOST, port=settings.TCP_PORT)
_tcp_server.set_pipeline_manager(pipeline_manager)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时加载模型 + 启动 TCP Server，关闭时优雅退出。"""
    # 1. 加载 YOLO 推理引擎（耗时操作，只做一次）
    logger.info("[Startup] initializing YOLO inference engine ...")
    engine.initialize(
        model_path=settings.YOLO_MODEL_PATH,
        device=settings.YOLO_DEVICE,
    )
    if engine.ready:
        logger.info("[Startup] YOLO engine ready")
    else:
        logger.warning("[Startup] YOLO engine NOT ready (no model file?), running in dummy mode")

    # 2. 启动 TCP Server
    await _tcp_server.start()

    yield  # ← 应用正常运行期间

    # 3. 关闭所有 Pipeline（取消协程 Task）
    await pipeline_manager.shutdown()

    # 4. 停止 TCP Server
    await _tcp_server.stop()

    logger.info("[Shutdown] done")


app = FastAPI(
    title="车辆检测与计数系统",
    description="STM32 采集 → TCP 传输 → YOLO 推理 → WebSocket 推送",
    version="0.3.0",
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
    return {
        "status": "ok",
        "version": "0.3.0",
        "yolo_ready": engine.ready,
        "active_devices": len(pipeline_manager.get_all_contexts()),
    }
