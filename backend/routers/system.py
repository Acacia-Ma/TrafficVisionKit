"""系统路由：健康状态、系统日志查询。"""
import time
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from models import Device, SystemLog
from routers.deps import AdminUser, DBSession
from schemas.system import SystemLogListResponse, SystemLogResponse, SystemStatusResponse

router = APIRouter(prefix="/api/system", tags=["system"])

_START_TIME = time.time()


@router.get("/status", response_model=SystemStatusResponse, summary="服务端健康状态（公开接口）")
async def system_status(session: DBSession) -> SystemStatusResponse:
    active_result = await session.execute(
        select(func.count()).select_from(Device).where(Device.is_active == True)  # noqa: E712
    )
    active_devices = active_result.scalar_one()

    return SystemStatusResponse(
        status="ok",
        version="0.2.0",
        uptime_seconds=round(time.time() - _START_TIME, 1),
        active_devices=active_devices,
    )


@router.get("/logs", response_model=SystemLogListResponse, summary="查询系统日志（admin）")
async def list_logs(
    session: DBSession,
    _admin: AdminUser,
    device_id: Optional[int] = Query(default=None),
    event_type: Optional[str] = Query(default=None),
    start: Optional[datetime] = Query(default=None),
    end: Optional[datetime] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> SystemLogListResponse:
    conditions = []
    if device_id is not None:
        conditions.append(SystemLog.device_id == device_id)
    if event_type is not None:
        conditions.append(SystemLog.event_type == event_type)
    if start is not None:
        conditions.append(SystemLog.created_at >= start)
    if end is not None:
        conditions.append(SystemLog.created_at <= end)

    total_q = select(func.count()).select_from(SystemLog)
    if conditions:
        total_q = total_q.where(*conditions)
    total = (await session.execute(total_q)).scalar_one()

    q = select(SystemLog).order_by(SystemLog.created_at.desc())
    if conditions:
        q = q.where(*conditions)
    q = q.offset((page - 1) * page_size).limit(page_size)
    rows = (await session.execute(q)).scalars().all()

    return SystemLogListResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=[SystemLogResponse.model_validate(r) for r in rows],
    )
