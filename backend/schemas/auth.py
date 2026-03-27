"""认证相关 Schema。"""
from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=32)
    password: str = Field(..., min_length=1, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(..., description="access_token 有效期（秒）")


class MeResponse(BaseModel):
    id: int
    username: str
    full_name: str
    role: str
    email: str | None
    must_change_password: bool

    model_config = {"from_attributes": True}
