"""日志脱敏、异常兜底与限流的回归测试。

重点守住三件事：
1. SSE 的 JWT 走 query string，绝不能出现在日志里
2. 异常不再把 str(e) 回给客户端（原来会带出 DB/上游报错细节）
3. 登录和 LLM 端点有限流，挡撞库和刷 LLM 成本
"""
import logging

import pytest

from backend.utils.logging_config import JsonFormatter, redact_query
from backend.utils.ratelimit import (
    LOGIN_MAX,
    _llm_bucket,
    _login_bucket,
    reset_all,
)


# ---------- query 脱敏 ----------


def test_redact_query_hides_token():
    """SSE 端点把 7 天有效期的 JWT 放在 ?token=，日志里必须打码。"""
    out = redact_query("message=hi&token=eyJhbGciOiJIUzI1NiIs.secret.sig")
    assert "eyJhbGciOiJIUzI1NiIs" not in out
    assert "secret" not in out
    assert "token=%2A%2A%2A" in out or "token=***" in out
    # 非敏感参数照常保留，便于排查
    assert "message=hi" in out


@pytest.mark.parametrize(
    "param", ["token", "access_token", "password", "api_key", "secret"]
)
def test_redact_query_covers_all_sensitive_params(param):
    out = redact_query(f"{param}=leakme&keep=1")
    assert "leakme" not in out
    assert "keep=1" in out


def test_redact_query_case_insensitive():
    assert "leakme" not in redact_query("TOKEN=leakme")


def test_redact_query_empty():
    assert redact_query("") == ""


# ---------- JSON 日志格式 ----------


def test_json_formatter_includes_extra_fields():
    rec = logging.LogRecord(
        name="backend.access", level=logging.INFO, pathname="x", lineno=1,
        msg="GET /api/v1/exams 200", args=(), exc_info=None,
    )
    rec.request_id = "abc123"
    rec.user_id = 7
    import json

    payload = json.loads(JsonFormatter().format(rec))
    assert payload["msg"] == "GET /api/v1/exams 200"
    assert payload["request_id"] == "abc123"
    assert payload["user_id"] == 7
    assert payload["level"] == "INFO"


# ---------- 请求日志中间件 ----------


def test_request_id_returned_in_header(client):
    """每个响应都带 X-Request-ID，便于用户报错时定位服务端日志。"""
    r = client.get("/health")
    assert r.headers.get("X-Request-ID")


def test_request_id_honors_inbound_header(client):
    r = client.get("/health", headers={"X-Request-ID": "trace-me-42"})
    assert r.headers["X-Request-ID"] == "trace-me-42"


def test_access_log_redacts_token_in_query(client, make_user, caplog):
    """access 日志记 query 时必须脱敏——这是 SSE token 泄漏的主要途径。"""
    u = make_user(email="sse@test.com")
    with caplog.at_level(logging.INFO, logger="backend.access"):
        # 走一个存在的 SSE 端点，token 会出现在 query 里
        client.get(
            "/api/v1/agent/stream",
            params={"message": "hi", "token": u["token"]},
        )
    logged = " ".join(
        str(getattr(r, "query", "")) + r.getMessage() for r in caplog.records
    )
    assert u["token"] not in logged, "JWT 泄漏进了 access 日志"


# ---------- 异常兜底 ----------


def test_unhandled_exception_hides_details(client, monkeypatch, caplog):
    """未捕获异常：客户端只拿 request_id，服务端记完整堆栈。"""
    from backend.api import main as main_mod

    secret_text = "DB password=hunter2 at 10.0.0.5:3306"

    @main_mod.app.get("/_boom_for_test")
    def _boom():
        raise RuntimeError(secret_text)

    with caplog.at_level(logging.ERROR, logger="backend.error"):
        r = client.get("/_boom_for_test")

    assert r.status_code == 500
    body = r.json()
    # 客户端拿不到异常内容
    assert secret_text not in r.text
    assert body["request_id"]
    # 服务端留了痕
    assert any("未捕获异常" in rec.getMessage() for rec in caplog.records)


# ---------- 限流 ----------


def test_login_rate_limited_by_ip(client, make_user):
    """撞库防护：同一 IP 超过配额后返回 429。"""
    reset_all()
    make_user(email="target@test.com", password="pw123456")
    bad = {"email": "target@test.com", "password": "wrong-password"}

    codes = [
        client.post("/api/v1/auth/login", json=bad).status_code
        for _ in range(LOGIN_MAX + 3)
    ]
    assert 401 in codes, "前几次应是正常的认证失败"
    assert 429 in codes, "超配额后应被限流"
    # 429 要带 Retry-After，客户端才知道等多久
    r = client.post("/api/v1/auth/login", json=bad)
    if r.status_code == 429:
        assert r.headers.get("Retry-After")


def test_login_rate_limit_blocks_correct_password_too(client, make_user):
    """限流是按 IP 计数的，配额耗尽后连正确密码也得等——这是有意的。"""
    reset_all()
    make_user(email="ok@test.com", password="pw123456")
    good = {"email": "ok@test.com", "password": "pw123456"}
    for _ in range(LOGIN_MAX):
        client.post("/api/v1/auth/login", json=good)
    assert client.post("/api/v1/auth/login", json=good).status_code == 429


def test_llm_endpoint_rate_limited_per_user(client, make_user, monkeypatch):
    """LLM 端点按用户限流，挡刷 DeepSeek 成本。"""
    reset_all()
    u = make_user(email="spender@test.com")

    # 不真调 LLM：让 run_smart_exam 直接抛已知业务异常，
    # 只关心限流是否在调用之前生效
    from backend.services import smart_exam as se

    def fake(*a, **kw):
        raise se.NoQuestionsError("题池为空")

    monkeypatch.setattr("backend.api.routers.exams.run_smart_exam", fake)

    codes = []
    for _ in range(_llm_bucket.max_hits + 2):
        r = client.post(
            "/api/v1/exams/smart-generate",
            json={"requirement": "出题", "level": "N1"},
            headers=u["headers"],
        )
        codes.append(r.status_code)
    assert 429 in codes, "LLM 端点超配额后应被限流"


def test_llm_rate_limit_is_per_user_not_global(client, make_user, monkeypatch):
    """一个用户刷满不能影响另一个用户。"""
    reset_all()
    from backend.services import smart_exam as se

    monkeypatch.setattr(
        "backend.api.routers.exams.run_smart_exam",
        lambda *a, **kw: (_ for _ in ()).throw(se.NoQuestionsError("空")),
    )
    heavy = make_user(email="heavy@test.com")
    light = make_user(email="light@test.com")

    for _ in range(_llm_bucket.max_hits + 2):
        client.post(
            "/api/v1/exams/smart-generate",
            json={"requirement": "出题", "level": "N1"},
            headers=heavy["headers"],
        )
    r = client.post(
        "/api/v1/exams/smart-generate",
        json={"requirement": "出题", "level": "N1"},
        headers=light["headers"],
    )
    assert r.status_code != 429, "限流串到了别的用户身上"


def test_bucket_window_resets(monkeypatch):
    """固定窗口过期后配额恢复。"""
    from backend.utils.ratelimit import _Bucket

    b = _Bucket(window_seconds=60, max_hits=2)
    assert b.check("k")[0] is True
    assert b.check("k")[0] is True
    assert b.check("k")[0] is False

    # 把时间推过窗口
    import backend.utils.ratelimit as rl

    base = rl.time.monotonic()
    monkeypatch.setattr(rl.time, "monotonic", lambda: base + 61)
    assert b.check("k")[0] is True


# ---------- 审计日志 ----------


def test_login_success_audited(client, make_user, caplog):
    reset_all()
    make_user(email="audit@test.com", password="pw123456")
    with caplog.at_level(logging.INFO, logger="backend.auth"):
        client.post(
            "/api/v1/auth/login",
            json={"email": "audit@test.com", "password": "pw123456"},
        )
    assert any("登录成功" in r.getMessage() for r in caplog.records)


def test_login_failure_audited_without_password(client, make_user, caplog):
    """登录失败要留痕，但日志里绝不能出现密码。"""
    reset_all()
    make_user(email="audit2@test.com", password="pw123456")
    with caplog.at_level(logging.WARNING, logger="backend.auth"):
        client.post(
            "/api/v1/auth/login",
            json={"email": "audit2@test.com", "password": "super-secret-pw"},
        )
    msgs = " ".join(r.getMessage() for r in caplog.records)
    assert "登录失败" in msgs
    assert "super-secret-pw" not in msgs


def test_admin_user_change_audited(client, make_user, caplog):
    """改角色/停用是权限敏感操作，必须记录谁改了谁。"""
    admin = make_user(email="root@test.com", role="admin")
    victim = make_user(email="victim@test.com", role="student")
    with caplog.at_level(logging.INFO, logger="backend.admin"):
        r = client.patch(
            f"/api/v1/admin/users/{victim['id']}",
            json={"is_active": False},
            headers=admin["headers"],
        )
    assert r.status_code == 200
    rec = next((x for x in caplog.records if "管理员修改用户" in x.getMessage()), None)
    assert rec is not None
    assert rec.actor_id == admin["id"]
    assert rec.target_user_id == victim["id"]
