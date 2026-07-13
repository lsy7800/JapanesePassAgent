"""FastAPI 依赖：数据库连接 + 身份认证。"""
import pymysql
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from pymysql.cursors import DictCursor

from crawler.config import DB_CONFIG
from backend.utils.security import decode_token

_bearer = HTTPBearer(auto_error=False)


def get_db():
    conn = pymysql.connect(cursorclass=DictCursor, **DB_CONFIG)
    try:
        yield conn
    finally:
        conn.close()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    conn=Depends(get_db),
):
    """解析 Bearer JWT，返回用户 dict。Token 缺失或无效时 401。"""
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录")
    try:
        payload = decode_token(credentials.credentials)
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token 无效或已过期")

    user_id = int(payload["sub"])
    with conn.cursor() as cur:
        cur.execute("SELECT id, email, role, is_active FROM users WHERE id = %s", (user_id,))
        user = cur.fetchone()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在")
    if not user["is_active"]:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="账号已停用")
    return user


def require_admin(user=Depends(get_current_user)):
    """在 get_current_user 基础上额外要求 admin 角色。"""
    if user["role"] != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要管理员权限")
    return user
