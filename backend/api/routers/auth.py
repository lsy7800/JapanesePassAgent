"""认证路由：注册 / 登录。

POST /api/v1/auth/register  注册新用户
POST /api/v1/auth/login     登录，返回 JWT
GET  /api/v1/auth/me        获取当前用户信息（需登录）
"""
import pymysql
from fastapi import APIRouter, Depends, HTTPException, Request
from pymysql.cursors import DictCursor

from backend.api.deps import get_db, get_current_user
from backend.schemas.user import LoginRequest, RegisterRequest, TokenResponse, UserOut
from backend.utils.logging_config import get_logger
from backend.utils.ratelimit import client_ip, limit_login, limit_register
from backend.utils.security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

logger = get_logger("backend.auth")


@router.post("/register", response_model=TokenResponse, status_code=201)
def register(payload: RegisterRequest, request: Request, conn=Depends(get_db), _=Depends(limit_register)):
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
    # 审计：注册只记 user_id 和 IP，不记邮箱明文以外的凭证信息
    logger.info(
        "用户注册",
        extra={"user_id": user_id, "role": payload.role, "client": client_ip(request)},
    )
    token = create_access_token(user_id, payload.email, payload.role)
    return TokenResponse(access_token=token, role=payload.role, email=payload.email)


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, conn=Depends(get_db), _=Depends(limit_login)):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, email, hashed_password, role, is_active FROM users WHERE email = %s",
            (payload.email,),
        )
        user = cur.fetchone()
    ip = client_ip(request)
    if not user or not verify_password(payload.password, user["hashed_password"]):
        # 审计：登录失败要留痕（撞库排查靠它），但不记密码，也不区分
        # "用户不存在"和"密码错"以免被用来枚举邮箱
        logger.warning("登录失败", extra={"client": ip})
        raise HTTPException(status_code=401, detail="邮箱或密码错误")
    if not user["is_active"]:
        logger.warning(
            "停用账号尝试登录", extra={"user_id": user["id"], "client": ip}
        )
        raise HTTPException(status_code=403, detail="账号已停用，请联系管理员")
    logger.info(
        "登录成功",
        extra={"user_id": user["id"], "role": user["role"], "client": ip},
    )
    token = create_access_token(user["id"], user["email"], user["role"])
    return TokenResponse(access_token=token, role=user["role"], email=user["email"])


@router.get("/me", response_model=UserOut)
def me(current_user=Depends(get_current_user)):
    return current_user
