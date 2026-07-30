"""JapanesePassAgent 后端服务入口。

开发启动：uv run uvicorn backend.api.main:app --reload
文档：http://localhost:8000/docs（仅非生产环境暴露）

生产由 ENV=production 收敛两处：CORS 只允许 ALLOWED_ORIGINS 列出的来源，
/docs、/redoc、/openapi.json 一并关闭（避免公开完整 API 结构）。
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from crawler.config import IS_PRODUCTION, allowed_origins

from backend.api.middleware import RequestLogMiddleware
from backend.api.routers import admin, agent, auth, chat_sessions, exams, questions, stats
from backend.utils.logging_config import setup_logging

# 尽早配置日志：路由模块 import 时可能就有日志输出
setup_logging()

# 生产关闭交互式文档与 schema：这三个出口会完整暴露 API 结构
_docs_kwargs = (
    {"docs_url": None, "redoc_url": None, "openapi_url": None} if IS_PRODUCTION else {}
)

app = FastAPI(
    title="JapanesePassAgent API",
    description="日语能力考试（JLPT）智能题库与 Agent 系统",
    version="0.1.0",
    **_docs_kwargs,
)

# 中间件注册顺序要留意：Starlette 中后注册的在外层。
# RequestLogMiddleware 必须先注册（处于内层），这样它兜异常时返回的 500
# 仍会经过外层的 CORS 中间件加上跨域头——否则浏览器读不到错误响应，
# 前端只能看到一个不明所以的网络错误。
app.add_middleware(RequestLogMiddleware)

# CORS 来源从 ALLOWED_ORIGINS 读取，不再用 "*"。
# 注意：allow_origins=["*"] 配 allow_credentials=True 本身是违反规范的组合，
# 浏览器对带凭证的请求会直接拒绝——之前"能用"只因为 token 走 Authorization 头。
# 同域部署（前端与 /api 由同一 nginx 提供）不产生跨域请求，留空即可。
_origins = allowed_origins()
if _origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(auth.router)
app.include_router(questions.router)
app.include_router(exams.router)
app.include_router(agent.router)
app.include_router(chat_sessions.router)
app.include_router(stats.router)
app.include_router(admin.router)


@app.get("/health", tags=["health"])
def health():
    return {"status": "ok"}
