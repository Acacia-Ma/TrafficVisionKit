"""设备管理相关 Schema。"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ── Device ──────────────────────────────────────────────────────────────────────

class DeviceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    ip_address: str = Field(..., pattern=r"^\d{1,3}(\.\d{1,3}){3}$")
    location: str = Field(..., min_length=1, max_length=100)


class DeviceUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=50)
    location: Optional[str] = Field(default=None, min_length=1, max_length=100)


class DeviceResponse(BaseModel):
    id: int
    name: str
    ip_address: str
    location: str
    is_active: bool
    last_seen_at: Optional[datetime]
    total_frames: int
    firmware_version: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── DeviceSettings ───────────────────────────────────────────────────────────────

class DeviceSettingsUpdate(BaseModel):
    line_y: Optional[int] = Field(default=None, ge=0, le=4096)
    confidence: Optional[float] = Field(default=None, ge=0.1, le=0.9)
    resolution_w: Optional[int] = Field(default=None, ge=160, le=3840)
    resolution_h: Optional[int] = Field(default=None, ge=120, le=2160)
    fps_limit: Optional[int] = Field(default=None, ge=1, le=60)
    alert_l2_threshold: Optional[int] = Field(default=None, ge=1, le=100)
    alert_l3_threshold: Optional[int] = Field(default=None, ge=1, le=100)
    alert_l4_threshold: Optional[int] = Field(default=None, ge=1, le=100)
    park_timeout_seconds: Optional[int] = Field(default=None, ge=5, le=3600)


class DeviceSettingsResponse(BaseModel):
    id: int
    device_id: int
    line_y: int
    confidence: float
    resolution_w: int
    resolution_h: int
    fps_limit: int
    alert_l2_threshold: int
    alert_l3_threshold: int
    alert_l4_threshold: int
    park_timeout_seconds: int
    updated_at: datetime

    model_config = {"from_attributes": True}
