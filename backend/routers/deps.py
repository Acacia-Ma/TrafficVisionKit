"""FastAPI 公共依赖注入：Token 解析、当前用户获取、权限检查。"""
from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.security import decode_access_token, decode_refresh_token, is_refresh_token_blacklisted
from database import get_session
from models import User

bearer_scheme = HTTPBearer(auto_error=False)


# ── Session 依赖 ────────────────────────────────────────────────────────────────

DBSession = Annotated[AsyncSession, Depends(get_session)]


# ── 当前用户依赖 ────────────────────────────────────────────────────────────────

async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    session: DBSession,
) -> User:
    """从 Bearer Token 中解析当前登录用户，token 无效/过期返回 401。"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"code": 1001, "message": "未认证或 Token 已失效"},
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise credentials_exception

    payload = decode_access_token(credentials.credentials)
    if payload is None:
        raise credentials_exception

    user_id: int = int(payload["sub"])
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise credentials_exception
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


# ── 角色权限依赖 ────────────────────────────────────────────────────────────────

async def require_admin(current_user: CurrentUser) -> User:
    """仅管理员可访问，非 admin 返回 403。"""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": 1003, "message": "需要管理员权限"},
        )
    return current_user


AdminUser = Annotated[User, Depends(require_admin)]


# ── 客户端 IP ───────────────────────────────────────────────────────────────────

def get_client_ip(request: Request) -> str:
    """获取请求客户端 IP（兼容反向代理 X-Forwarded-For）。"""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


ClientIP = Annotated[str, Depends(get_client_ip)]


# ── Refresh Token Cookie 依赖 ───────────────────────────────────────────────────

async def get_refresh_token_from_cookie(
    refresh_token: Annotated[str | None, Cookie(alias="refresh_token")] = None,
) -> str:
    """从 HttpOnly Cookie 中读取 refresh_token，不存在则返回 401。"""
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": 1004, "message": "refresh_token 缺失"},
        )
    return refresh_token


RefreshTokenCookie = Annotated[str, Depends(get_refresh_token_from_cookie)]
