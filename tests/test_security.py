"""security.py 纯单元测试：密码哈希 + JWT。无需数据库。"""
from datetime import datetime, timedelta, timezone

import pytest
from jose import JWTError, jwt

from backend.utils import security


def test_hash_password_verifies():
    hashed = security.hash_password("s3cret-pw")
    assert hashed != "s3cret-pw"  # 不是明文
    assert security.verify_password("s3cret-pw", hashed)
    assert not security.verify_password("wrong-pw", hashed)


def test_hash_password_salted():
    # 相同明文两次哈希应不同（每次随机盐）
    assert security.hash_password("same") != security.hash_password("same")


def test_token_roundtrip():
    token = security.create_access_token(42, "u@test.com", "admin")
    payload = security.decode_token(token)
    assert payload["sub"] == "42"
    assert payload["email"] == "u@test.com"
    assert payload["role"] == "admin"


def test_decode_expired_token_raises():
    # 手工造一个已过期的 token
    expired = datetime.now(timezone.utc) - timedelta(minutes=1)
    token = jwt.encode(
        {"sub": "1", "exp": expired},
        security._secret(),
        algorithm=security.ALGORITHM,
    )
    with pytest.raises(JWTError):
        security.decode_token(token)


def test_decode_tampered_token_raises():
    token = security.create_access_token(1, "u@test.com", "student")
    # 篡改中段，破坏签名
    head, mid, sig = token.split(".")
    tampered = f"{head}.{mid}x.{sig}"
    with pytest.raises(JWTError):
        security.decode_token(tampered)


def test_decode_wrong_secret_raises():
    token = jwt.encode({"sub": "1"}, "some-other-secret", algorithm=security.ALGORITHM)
    with pytest.raises(JWTError):
        security.decode_token(token)
