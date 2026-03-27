"""系统日志相关 Schema。"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class SystemLogResponse(BaseModel):
    id: int
    device_id: Optional[int]
    event_type: str
    message: str
    operator_ip: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class SystemLogListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[SystemLogResponse]


class SystemStatusResponse(BaseModel):
    status: str
    version: str
    uptime_seconds: float
    active_devices: int
