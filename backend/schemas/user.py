"""用户相关 Pydantic 模型。"""
from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, description="密码至少6位")
    # 公开注册只允许 student；admin 账号通过后台命令行创建
    role: str = Field(default="student", pattern="^student$")


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    email: str


class UserOut(BaseModel):
    id: int
    email: str
    role: str
