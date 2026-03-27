"""routers 包 —— 导出所有 APIRouter，供 main.py 统一挂载。"""
from routers.auth import router as auth_router
from routers.devices import router as devices_router
from routers.history import router as history_router
from routers.system import router as system_router
from routers.users import router as users_router
from routers.ws import router as ws_router

__all__ = [
    "auth_router",
    "devices_router",
    "history_router",
    "system_router",
    "users_router",
    "ws_router",
]
