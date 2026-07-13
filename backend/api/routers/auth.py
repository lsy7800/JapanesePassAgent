"""认证路由：注册 / 登录。

POST /api/v1/auth/register  注册新用户
POST /api/v1/auth/login     登录，返回 JWT
GET  /api/v1/auth/me        获取当前用户信息（需登录）
"""
import pymysql
from fastapi import APIRouter, Depends, HTTPException
from pymysql.cursors import DictCursor

from backend.api.deps import get_db, get_current_user
from backend.schemas.user import LoginRequest, RegisterRequest, TokenResponse, UserOut
from backend.utils.security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=201)
def register(payload: RegisterRequest, conn=Depends(get_db)):
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM users WHERE email = %s", (payload.email,))
        if cur.fetchone():
            raise HTTPException(status_code=409, detail="邮箱已注册")
        cur.execute(
            "INSERT INTO users (email, hashed_password, role) VALUES (%s, %s, %s)",
            (payload.email, hash_password(payload.password), payload.role),
        )
        user_id = cur.lastrowid
    conn.commit()
    token = create_access_token(user_id, payload.email, payload.role)
    return TokenResponse(access_token=token, role=payload.role, email=payload.email)


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, conn=Depends(get_db)):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, email, hashed_password, role, is_active FROM users WHERE email = %s",
            (payload.email,),
        )
        user = cur.fetchone()
    if not user or not verify_password(payload.password, user["hashed_password"]):
        raise HTTPException(status_code=401, detail="邮箱或密码错误")
    if not user["is_active"]:
        raise HTTPException(status_code=403, detail="账号已停用，请联系管理员")
    token = create_access_token(user["id"], user["email"], user["role"])
    return TokenResponse(access_token=token, role=user["role"], email=user["email"])


@router.get("/me", response_model=UserOut)
def me(current_user=Depends(get_current_user)):
    return current_user
