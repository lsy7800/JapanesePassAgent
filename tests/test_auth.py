"""认证接口测试：注册 / 登录 / me。"""


def test_register_success(client):
    r = client.post(
        "/api/v1/auth/register",
        json={"email": "new@test.com", "password": "pw123456"},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["email"] == "new@test.com"
    assert body["role"] == "student"
    assert body["access_token"]


def test_register_duplicate_email(client, make_user):
    make_user(email="dup@test.com")
    r = client.post(
        "/api/v1/auth/register",
        json={"email": "dup@test.com", "password": "pw123456"},
    )
    assert r.status_code == 409


def test_register_rejects_admin_role(client):
    # 公开注册不允许自封 admin（schema pattern 限制）
    r = client.post(
        "/api/v1/auth/register",
        json={"email": "hacker@test.com", "password": "pw123456", "role": "admin"},
    )
    assert r.status_code == 422


def test_login_success(client, make_user):
    u = make_user(email="login@test.com", password="pw123456")
    r = client.post(
        "/api/v1/auth/login",
        json={"email": u["email"], "password": "pw123456"},
    )
    assert r.status_code == 200
    assert r.json()["access_token"]


def test_login_wrong_password(client, make_user):
    make_user(email="wp@test.com", password="pw123456")
    r = client.post(
        "/api/v1/auth/login",
        json={"email": "wp@test.com", "password": "WRONG-pw"},
    )
    assert r.status_code == 401


def test_login_unknown_email(client):
    r = client.post(
        "/api/v1/auth/login",
        json={"email": "ghost@test.com", "password": "whatever"},
    )
    assert r.status_code == 401


def test_login_inactive_forbidden(client, make_user):
    make_user(email="off@test.com", password="pw123456", is_active=False)
    r = client.post(
        "/api/v1/auth/login",
        json={"email": "off@test.com", "password": "pw123456"},
    )
    assert r.status_code == 403


def test_me_with_token(client, make_user):
    u = make_user(email="me@test.com")
    r = client.get("/api/v1/auth/me", headers=u["headers"])
    assert r.status_code == 200
    body = r.json()
    assert body["email"] == "me@test.com"
    assert body["id"] == u["id"]


def test_me_without_token(client):
    assert client.get("/api/v1/auth/me").status_code == 401


def test_me_bad_token(client):
    r = client.get(
        "/api/v1/auth/me", headers={"Authorization": "Bearer not.a.jwt"}
    )
    assert r.status_code == 401


def test_inactive_token_rejected(client, make_user):
    # 已登录用户被停用后，旧 token 立即失效（get_current_user 校验 is_active）
    u = make_user(email="ban@test.com", is_active=False)
    r = client.get("/api/v1/auth/me", headers=u["headers"])
    assert r.status_code == 401
