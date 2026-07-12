"""JWT + bcrypt 工具函数。

直接使用 bcrypt 5.x 库（passlib 1.7.4 与 bcrypt 4+ 不兼容）。
"""
from datetime import datetime, timedelta, timezone

import bcrypt
from jose import JWTError, jwt

from crawler.config import require

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7天


def _secret() -> str:
    return require("JWT_SECRET")


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def create_access_token(user_id: int, email: str, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": str(user_id), "email": email, "role": role, "exp": expire}
    return jwt.encode(payload, _secret(), algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    """解码 JWT，失败抛 JWTError。"""
    return jwt.decode(token, _secret(), algorithms=[ALGORITHM])
