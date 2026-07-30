"""生产环境收敛项的回归测试：CORS 来源白名单 + 关闭 /docs。

这些配置在 import 时求值（FastAPI 的 docs_url 和 add_middleware 都只在建 app 时生效），
所以每个用例都要重设环境变量再重新 import backend.api.main，不能复用 conftest 的
client fixture。用 importlib.reload 拿到按当前环境重建的 app。
"""
import importlib

import pytest
from fastapi.testclient import TestClient


def _app_with_env(monkeypatch, **env):
    """按给定环境变量重建 app（配置在 import 时求值，必须 reload）。"""
    for k, v in env.items():
        if v is None:
            monkeypatch.delenv(k, raising=False)
        else:
            monkeypatch.setenv(k, v)
    import crawler.config
    import backend.api.main

    importlib.reload(crawler.config)
    importlib.reload(backend.api.main)
    return backend.api.main.app


@pytest.fixture(autouse=True)
def _restore_modules():
    """用例改过的模块状态还原，避免污染同一进程里的其他测试。"""
    yield
    import crawler.config
    import backend.api.main

    importlib.reload(crawler.config)
    importlib.reload(backend.api.main)


# ---------- 关闭调试出口 ----------


def test_docs_closed_in_production(monkeypatch):
    app = _app_with_env(monkeypatch, ENV="production", ALLOWED_ORIGINS=None)
    c = TestClient(app)
    # /openapi.json 一并关闭：只关 /docs 仍会暴露完整 API 结构
    assert c.get("/docs").status_code == 404
    assert c.get("/redoc").status_code == 404
    assert c.get("/openapi.json").status_code == 404


def test_docs_open_in_development(monkeypatch):
    app = _app_with_env(monkeypatch, ENV="development", ALLOWED_ORIGINS=None)
    c = TestClient(app)
    assert c.get("/docs").status_code == 200
    assert c.get("/openapi.json").status_code == 200


def test_health_still_public_in_production(monkeypatch):
    """健康检查不能被收敛掉，反代和容器探针要用。"""
    app = _app_with_env(monkeypatch, ENV="production", ALLOWED_ORIGINS=None)
    assert TestClient(app).get("/health").status_code == 200


# ---------- CORS 白名单 ----------


def _allow_origin(app, origin):
    r = TestClient(app).get("/health", headers={"Origin": origin})
    return r.headers.get("access-control-allow-origin")


def test_cors_allows_configured_origins(monkeypatch):
    app = _app_with_env(
        monkeypatch,
        ENV="production",
        ALLOWED_ORIGINS="https://www.example.com,https://admin.example.com",
    )
    assert _allow_origin(app, "https://www.example.com") == "https://www.example.com"
    assert _allow_origin(app, "https://admin.example.com") == "https://admin.example.com"


def test_cors_rejects_unlisted_origin(monkeypatch):
    app = _app_with_env(
        monkeypatch, ENV="production", ALLOWED_ORIGINS="https://www.example.com"
    )
    assert _allow_origin(app, "https://evil.example.com") is None


def test_cors_never_wildcards_in_production(monkeypatch):
    """回归护栏：曾经是 allow_origins=["*"]，任何路径都不许回落成通配。"""
    app = _app_with_env(monkeypatch, ENV="production", ALLOWED_ORIGINS=None)
    assert _allow_origin(app, "https://evil.example.com") is None
    # 未配置来源时干脆不挂 CORS 中间件（同域部署场景）
    assert not any("CORS" in str(m) for m in app.user_middleware)


def test_cors_defaults_to_dev_ports_when_unset(monkeypatch):
    """开发环境留空时回落到本地两个 vite 端口，方便联调。"""
    app = _app_with_env(monkeypatch, ENV="development", ALLOWED_ORIGINS=None)
    assert _allow_origin(app, "http://localhost:5174") == "http://localhost:5174"
    assert _allow_origin(app, "https://evil.example.com") is None


def test_origins_tolerate_whitespace_and_trailing_slash(monkeypatch):
    """.env 里手写难免带空格或结尾斜杠；Origin 头不含结尾斜杠，需归一化后才匹配得上。"""
    app = _app_with_env(
        monkeypatch,
        ENV="production",
        ALLOWED_ORIGINS=" https://www.example.com/ , https://admin.example.com ",
    )
    assert _allow_origin(app, "https://www.example.com") == "https://www.example.com"
    assert _allow_origin(app, "https://admin.example.com") == "https://admin.example.com"
