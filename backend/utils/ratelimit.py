"""进程内限流：固定窗口计数器。

为什么自己写而不用 slowapi：这套栈里没有 Redis，slowapi 的默认存储同样是
进程内内存，收益只是少写 60 行，却多一个无上界的依赖（pyproject 里所有依赖
都是 `>=`，能少一个是一个）。

**已知局限**（多 worker 部署前必须知道）：
计数在进程内存里，`uvicorn --workers N` 会让每个 worker 各算一份，实际配额
变成 N 倍；重启即清零。当前 docker-compose.prod.yml 是单 worker，够用。
要扩多 worker 或多实例，得换成 Redis 后端——那时把 _Bucket 换掉即可，
check() 的接口不用动。

限的是两类风险：
- /auth/login 撞库（按 IP）
- LLM 端点被刷成本（按用户），DeepSeek 是按 token 计费的
"""
import threading
import time
from dataclasses import dataclass, field

from fastapi import HTTPException, Request, status

from crawler.config import get


def _int_env(name: str, default: int) -> int:
    raw = get(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return int(str(raw).strip())
    except ValueError:
        return default


# 可通过环境变量调整；默认值偏宽松，够正常使用又能挡住脚本
LOGIN_MAX = _int_env("RATELIMIT_LOGIN_PER_MIN", 10)          # 每 IP 每分钟登录尝试
REGISTER_MAX = _int_env("RATELIMIT_REGISTER_PER_HOUR", 20)    # 每 IP 每小时注册
LLM_MAX = _int_env("RATELIMIT_LLM_PER_MIN", 10)               # 每用户每分钟 LLM 调用


@dataclass
class _Bucket:
    """固定窗口计数器。窗口过期就整体重置。"""

    window_seconds: int
    max_hits: int
    _hits: dict = field(default_factory=dict)  # key -> [窗口起点, 计数]
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def check(self, key: str) -> tuple[bool, int]:
        """返回 (是否允许, 距窗口重置的秒数)。"""
        now = time.monotonic()
        with self._lock:
            start, count = self._hits.get(key, (now, 0))
            if now - start >= self.window_seconds:
                # 窗口已过，重新开始
                self._hits[key] = (now, 1)
                return True, self.window_seconds
            retry_after = int(self.window_seconds - (now - start)) + 1
            if count >= self.max_hits:
                return False, retry_after
            self._hits[key] = (start, count + 1)
            return True, retry_after

    def reset(self) -> None:
        """仅测试用：清空所有计数。"""
        with self._lock:
            self._hits.clear()

    def _prune(self, now: float) -> None:
        """清掉过期条目，避免 key 无限增长（被大量 IP 打时）。"""
        expired = [
            k for k, (start, _) in self._hits.items()
            if now - start >= self.window_seconds
        ]
        for k in expired:
            del self._hits[k]


_login_bucket = _Bucket(window_seconds=60, max_hits=LOGIN_MAX)
_register_bucket = _Bucket(window_seconds=3600, max_hits=REGISTER_MAX)
_llm_bucket = _Bucket(window_seconds=60, max_hits=LLM_MAX)

# 每处理这么多次请求做一轮过期清理，避免每次都遍历
_PRUNE_EVERY = 500
_counter = 0
_counter_lock = threading.Lock()


def _maybe_prune() -> None:
    global _counter
    with _counter_lock:
        _counter += 1
        due = _counter % _PRUNE_EVERY == 0
    if due:
        now = time.monotonic()
        for b in (_login_bucket, _register_bucket, _llm_bucket):
            with b._lock:
                b._prune(now)


def client_ip(request: Request) -> str:
    """取真实客户端 IP。

    nginx 反代后 request.client.host 是反代自己的地址，真实 IP 在
    X-Forwarded-For 的第一个（deploy/proxy-common.conf 里设置）。
    注意：这个头可被伪造，但配合固定窗口限流足够——攻击者伪造头能绕过
    自己的配额，却也拿不到别人的额度。
    """
    xff = request.headers.get("X-Forwarded-For", "")
    if xff:
        first = xff.split(",")[0].strip()
        if first:
            return first
    return request.client.host if request.client else "unknown"


def _enforce(bucket: _Bucket, key: str, message: str) -> None:
    _maybe_prune()
    allowed, retry_after = bucket.check(key)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=message,
            headers={"Retry-After": str(retry_after)},
        )


def limit_login(request: Request) -> None:
    """FastAPI 依赖：按 IP 限制登录尝试，挡撞库。"""
    _enforce(
        _login_bucket,
        f"login:{client_ip(request)}",
        "登录尝试过于频繁，请稍后再试",
    )


def limit_register(request: Request) -> None:
    """FastAPI 依赖：按 IP 限制注册，挡批量注册。"""
    _enforce(
        _register_bucket,
        f"register:{client_ip(request)}",
        "注册过于频繁，请稍后再试",
    )


def limit_llm_by_user(user_id: int) -> None:
    """按用户限制 LLM 调用。

    不做成 FastAPI 依赖是因为 SSE 端点的用户身份要先解 query token 才知道
    （auth_by_query_token），拿到 user_id 后再手动调用。
    """
    _enforce(
        _llm_bucket,
        f"llm:{user_id}",
        "AI 功能调用过于频繁，请稍后再试",
    )


def reset_all() -> None:
    """仅测试用：清空全部计数，避免用例间互相影响。"""
    for b in (_login_bucket, _register_bucket, _llm_bucket):
        b.reset()
