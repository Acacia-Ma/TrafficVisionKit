"""JWT 签发/验证 + bcrypt 密码哈希工具（不依赖 passlib，直接使用 bcrypt 原生库）。"""
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from jose import JWTError, jwt

from core.config import get_settings

# ── 内存黑名单（refresh_token jti → 过期时间戳）────────────────────────────────
# 服务重启后清空，属已知限制（见设计稿 6.3 节）
_refresh_blacklist: dict[str, datetime] = {}


# ── 密码工具 ────────────────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    """使用 bcrypt(cost=12) 对明文密码进行哈希，返回 60 字节字符串。"""
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt(rounds=12)).decode()


def verify_password(plain: str, hashed: str) -> bool:
    """验证明文密码与哈希是否匹配。"""
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except Exception:
        return False


# ── JWT 工具 ────────────────────────────────────────────────────────────────────

def _settings():
    return get_settings()


def create_access_token(user_id: int, username: str, role: str) -> str:
    """签发 access_token（有效期由配置决定，默认 60 分钟）。"""
    s = _settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "username": username,
        "role": role,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=s.ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, s.JWT_SECRET_KEY, algorithm=s.JWT_ALGORITHM)


def create_refresh_token(user_id: int) -> tuple[str, str]:
    """签发 refresh_token，返回 (token, jti)。
    jti 用于黑名单追踪（旋转策略）。
    """
    import uuid
    s = _settings()
    now = datetime.now(timezone.utc)
    jti = str(uuid.uuid4())
    payload = {
        "sub": str(user_id),
        "type": "refresh",
        "jti": jti,
        "iat": now,
        "exp": now + timedelta(days=s.REFRESH_TOKEN_EXPIRE_DAYS),
    }
    return jwt.encode(payload, s.JWT_SECRET_KEY, algorithm=s.JWT_ALGORITHM), jti


def decode_access_token(token: str) -> Optional[dict]:
    """解码并验证 access_token，返回 payload 或 None（过期/无效）。"""
    s = _settings()
    try:
        payload = jwt.decode(token, s.JWT_SECRET_KEY, algorithms=[s.JWT_ALGORITHM])
        if payload.get("type") != "access":
            return None
        return payload
    except JWTError:
        return None


def decode_refresh_token(token: str) -> Optional[dict]:
    """解码并验证 refresh_token，返回 payload 或 None。"""
    s = _settings()
    try:
        payload = jwt.decode(token, s.JWT_SECRET_KEY, algorithms=[s.JWT_ALGORITHM])
        if payload.get("type") != "refresh":
            return None
        return payload
    except JWTError:
        return None


# ── 黑名单管理 ──────────────────────────────────────────────────────────────────

def blacklist_refresh_token(jti: str, exp: datetime) -> None:
    """将已旋转或已登出的 refresh_token jti 加入内存黑名单。"""
    _purge_expired_blacklist()
    _refresh_blacklist[jti] = exp


def is_refresh_token_blacklisted(jti: str) -> bool:
    """检查 jti 是否在黑名单中。"""
    _purge_expired_blacklist()
    return jti in _refresh_blacklist


def _purge_expired_blacklist() -> None:
    """清理已过期的黑名单条目（惰性清理，避免内存泄漏）。"""
    now = datetime.now(timezone.utc)
    expired = [k for k, v in _refresh_blacklist.items() if v < now]
    for k in expired:
        del _refresh_blacklist[k]
