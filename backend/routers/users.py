"""用户管理路由（仅 admin 可操作，自己修改密码除外）。"""
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from core.security import hash_password, verify_password
from models import SystemLog, User
from routers.deps import AdminUser, ClientIP, CurrentUser, DBSession
from schemas.user import (
    ChangePassword,
    PasswordReset,
    UserCreate,
    UserListResponse,
    UserResponse,
    UserUpdate,
)

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("", response_model=UserListResponse, summary="分页查询用户列表")
async def list_users(
    session: DBSession,
    _admin: AdminUser,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> UserListResponse:
    total_result = await session.execute(select(func.count()).select_from(User))
    total = total_result.scalar_one()

    result = await session.execute(
        select(User)
        .order_by(User.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    users = result.scalars().all()
    return UserListResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=[UserResponse.model_validate(u) for u in users],
    )


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED, summary="创建用户")
async def create_user(
    body: UserCreate,
    session: DBSession,
    _admin: AdminUser,
    client_ip: ClientIP,
) -> UserResponse:
    existing = await session.execute(select(User).where(User.username == body.username))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": 2001, "message": "用户名已存在"},
        )
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    user = User(
        username=body.username,
        password_hash=hash_password(body.password),
        full_name=body.full_name,
        email=body.email,
        role=body.role,
        must_change_password=True,
        created_at=now,
        updated_at=now,
    )
    session.add(user)
    session.add(SystemLog(
        event_type="info",
        message=f"管理员创建用户 {body.username}（IP: {client_ip}）",
        operator_ip=client_ip,
        created_at=now,
    ))
    await session.commit()
    await session.refresh(user)
    return UserResponse.model_validate(user)


@router.put("/{user_id}", response_model=UserResponse, summary="更新用户信息")
async def update_user(
    user_id: int,
    body: UserUpdate,
    session: DBSession,
    _admin: AdminUser,
) -> UserResponse:
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": 2002, "message": "用户不存在"})

    if body.full_name is not None:
        user.full_name = body.full_name
    if body.email is not None:
        user.email = body.email
    if body.role is not None:
        user.role = body.role
    if body.is_active is not None:
        user.is_active = body.is_active

    await session.commit()
    await session.refresh(user)
    return UserResponse.model_validate(user)


@router.put("/{user_id}/password", status_code=status.HTTP_204_NO_CONTENT, summary="管理员重置密码")
async def reset_password(
    user_id: int,
    body: PasswordReset,
    session: DBSession,
    _admin: AdminUser,
    client_ip: ClientIP,
) -> None:
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": 2002, "message": "用户不存在"})

    user.password_hash = hash_password(body.new_password)
    user.must_change_password = True
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    session.add(SystemLog(
        event_type="user_password_change",
        message=f"管理员重置用户 {user.username} 的密码（IP: {client_ip}）",
        operator_ip=client_ip,
        created_at=now,
    ))
    await session.commit()


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT, summary="删除用户（软删除）")
async def delete_user(
    user_id: int,
    session: DBSession,
    admin: AdminUser,
) -> None:
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": 2002, "message": "用户不存在"})
    if user.id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": 2003, "message": "不能删除自己"},
        )
    user.is_active = False
    await session.commit()


@router.put("/me/password", status_code=status.HTTP_204_NO_CONTENT, summary="当前用户修改自己的密码")
async def change_my_password(
    body: ChangePassword,
    session: DBSession,
    current_user: CurrentUser,
    client_ip: ClientIP,
) -> None:
    if not verify_password(body.old_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": 2004, "message": "原密码错误"},
        )
    current_user.password_hash = hash_password(body.new_password)
    current_user.must_change_password = False
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    session.add(SystemLog(
        event_type="user_password_change",
        message=f"用户 {current_user.username} 修改了自己的密码（IP: {client_ip}）",
        operator_ip=client_ip,
        created_at=now,
    ))
    await session.commit()
