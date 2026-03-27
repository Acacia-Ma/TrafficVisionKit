"""schemas 包 —— 所有 Pydantic 请求/响应模型。"""
from schemas.auth import LoginRequest, MeResponse, TokenResponse
from schemas.device import (
    DeviceCreate,
    DeviceResponse,
    DeviceSettingsResponse,
    DeviceSettingsUpdate,
    DeviceUpdate,
)
from schemas.history import (
    AlertListResponse,
    AlertResponse,
    AlertResolveRequest,
    HeatmapResponse,
    HourlyStatisticsResponse,
    SessionListResponse,
    SessionResponse,
    TrafficRecordResponse,
)
from schemas.system import SystemLogListResponse, SystemLogResponse, SystemStatusResponse
from schemas.user import (
    ChangePassword,
    PasswordReset,
    UserCreate,
    UserListResponse,
    UserResponse,
    UserUpdate,
)

__all__ = [
    "LoginRequest", "MeResponse", "TokenResponse",
    "DeviceCreate", "DeviceUpdate", "DeviceResponse",
    "DeviceSettingsUpdate", "DeviceSettingsResponse",
    "AlertListResponse", "AlertResponse", "AlertResolveRequest",
    "HeatmapResponse", "HourlyStatisticsResponse",
    "SessionListResponse", "SessionResponse", "TrafficRecordResponse",
    "SystemLogListResponse", "SystemLogResponse", "SystemStatusResponse",
    "UserCreate", "UserUpdate", "UserResponse", "UserListResponse",
    "PasswordReset", "ChangePassword",
]
