"""认证路由：登录、刷新 Token、登出、获取当前用户信息。"""
import time
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select

from core.config import get_settings
from core.security import (
    blacklist_refresh_token,
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    is_refresh_token_blacklisted,
    verify_password,
)
from models import SystemLog, User
from routers.deps import ClientIP, CurrentUser, DBSession, RefreshTokenCookie
from schemas.auth import LoginRequest, MeResponse, TokenResponse

router = APIRouter(prefix="/api/auth", tags=["auth"])

# 登录失败计数（内存，key=username），结构：{username: {"count": int, "locked_until": float}}
_login_failures: dict[str, dict] = {}
_MAX_FAILURES = 5
_LOCK_SECONDS = 300  # 5 分钟


def _check_lock(username: str) -> None:
    info = _login_failures.get(username)
    if info and info["count"] >= _MAX_FAILURES:
        remaining = info["locked_until"] - time.time()
        if remaining > 0:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "code": 1002,
                    "message": f"账号已锁定，请 {int(remaining)} 秒后重试",
                },
            )
        else:
            del _login_failures[username]


def _record_failure(username: str) -> None:
    info = _login_failures.setdefault(username, {"count": 0, "locked_until": 0.0})
    info["count"] += 1
    info["locked_until"] = time.time() + _LOCK_SECONDS


def _clear_failure(username: str) -> None:
    _login_failures.pop(username, None)


@router.post("/login", response_model=TokenResponse, summary="用户登录")
async def login(
    body: LoginRequest,
    response: Response,
    session: DBSession,
    client_ip: ClientIP,
) -> TokenResponse:
    settings = get_settings()

    _check_lock(body.username)

    result = await session.execute(
        select(User).where(User.username == body.username)
    )
    user = result.scalar_one_or_none()

    if user is None or not verify_password(body.password, user.password_hash):
        _record_failure(body.username)
        # 写入失败日志
        session.add(SystemLog(
            event_type="user_failed_login",
            message=f"用户 {body.username} 登录失败（IP: {client_ip}）",
            operator_ip=client_ip,
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        ))
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": 1001, "message": "用户名或密码错误"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": 1006, "message": "账号已被禁用"},
        )

    _clear_failure(body.username)

    access_token = create_access_token(user.id, user.username, user.role)
    refresh_token, _jti = create_refresh_token(user.id)

    # 更新最后登录时间
    user.last_login_at = datetime.now(timezone.utc).replace(tzinfo=None)
    session.add(SystemLog(
        event_type="user_login",
        message=f"用户 {user.username} 登录成功（IP: {client_ip}）",
        operator_ip=client_ip,
        created_at=datetime.now(timezone.utc).replace(tzinfo=None),
    ))
    await session.commit()

    # refresh_token 写入 HttpOnly Cookie
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="strict",
        domain=settings.COOKIE_DOMAIN or None,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        path="/api/auth/refresh",
    )

    return TokenResponse(
        access_token=access_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/refresh", response_model=TokenResponse, summary="刷新 access_token")
async def refresh(
    response: Response,
    session: DBSession,
    refresh_token: RefreshTokenCookie,
) -> TokenResponse:
    settings = get_settings()

    payload = decode_refresh_token(refresh_token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": 1005, "message": "refresh_token 无效或已过期"},
        )

    jti: str = payload["jti"]
    user_id: int = int(payload["sub"])

    # 检测已用过的旧 token（重放攻击）
    if is_refresh_token_blacklisted(jti):
        # 可能发生 token 泄漏，写日志并强制全部失效
        session.add(SystemLog(
            event_type="user_failed_login",
            message=f"检测到已吊销的 refresh_token 被重放（user_id={user_id}），强制登出",
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        ))
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": 1007, "message": "Token 安全异常，请重新登录"},
        )

    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": 1005, "message": "用户不存在或已禁用"},
        )

    # 旋转：旧 token 加黑名单
    from datetime import datetime as dt
    exp = dt.fromtimestamp(payload["exp"], tz=timezone.utc)
    blacklist_refresh_token(jti, exp)

    # 签发新 token 对
    new_access = create_access_token(user.id, user.username, user.role)
    new_refresh, _new_jti = create_refresh_token(user.id)

    response.set_cookie(
        key="refresh_token",
        value=new_refresh,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="strict",
        domain=settings.COOKIE_DOMAIN or None,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        path="/api/auth/refresh",
    )

    return TokenResponse(
        access_token=new_access,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="登出")
async def logout(
    response: Response,
    current_user: CurrentUser,
    refresh_token: str | None = None,
) -> None:
    if refresh_token:
        payload = decode_refresh_token(refresh_token)
        if payload:
            from datetime import datetime as dt
            exp = dt.fromtimestamp(payload["exp"], tz=timezone.utc)
            blacklist_refresh_token(payload["jti"], exp)

    response.delete_cookie(key="refresh_token", path="/api/auth/refresh")


@router.get("/me", response_model=MeResponse, summary="获取当前用户信息")
async def me(current_user: CurrentUser) -> MeResponse:
    return MeResponse.model_validate(current_user)
