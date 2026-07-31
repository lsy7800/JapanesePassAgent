"""请求日志中间件 + 未捕获异常兜底。

两件事：
1. 每个请求记一行 access 日志，带 request_id、耗时、状态码。
   query string 经 redact_query 脱敏——SSE 端点把 JWT 放在 ?token=，
   原样记录等于把 7 天有效期的凭证写进日志。
2. 未捕获异常在服务端记完整堆栈，只回客户端一个 request_id。
   之前的做法是把 str(e) 直接返回给客户端（可能带出 DB 连接信息或上游
   API 报错体），服务端反而什么都不留。
"""
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from backend.utils.logging_config import get_logger, redact_query

logger = get_logger("backend.access")
error_logger = get_logger("backend.error")

# 健康检查不记日志：容器探针每 30s 一次，会把日志淹掉
_SKIP_PATHS = {"/health", "/nginx-health"}


class RequestLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
        # 供路由处理函数取用（异常处理里要把它回给客户端）
        request.state.request_id = request_id

        start = time.perf_counter()
        path = request.url.path

        try:
            response = await call_next(request)
        except Exception:
            elapsed_ms = round((time.perf_counter() - start) * 1000, 1)
            # exc_info=True 把完整堆栈写进服务端日志
            error_logger.exception(
                "未捕获异常",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": path,
                    "query": redact_query(request.url.query),
                    "elapsed_ms": elapsed_ms,
                    "client": request.client.host if request.client else None,
                },
            )
            # 只回 request_id，不回异常内容——避免泄漏内部细节
            return JSONResponse(
                status_code=500,
                content={
                    "detail": "服务器内部错误，请联系管理员并提供 request_id",
                    "request_id": request_id,
                },
                headers={"X-Request-ID": request_id},
            )

        elapsed_ms = round((time.perf_counter() - start) * 1000, 1)
        response.headers["X-Request-ID"] = request_id

        if path not in _SKIP_PATHS:
            # 4xx 用 warning，5xx 用 error，其余 info——便于按级别筛告警
            if response.status_code >= 500:
                log = logger.error
            elif response.status_code >= 400:
                log = logger.warning
            else:
                log = logger.info
            log(
                f"{request.method} {path} {response.status_code}",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": path,
                    "query": redact_query(request.url.query),
                    "status": response.status_code,
                    "elapsed_ms": elapsed_ms,
                    "client": request.client.host if request.client else None,
                },
            )
        return response
