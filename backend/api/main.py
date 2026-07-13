"""JapanesePassAgent 后端服务入口。

启动：uv run uvicorn backend.api.main:app --reload
文档：http://localhost:8000/docs
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routers import admin, agent, auth, exams, questions, stats

app = FastAPI(
    title="JapanesePassAgent API",
    description="日语能力考试（JLPT）智能题库与 Agent 系统",
    version="0.1.0",
)

# 前端联调阶段放开 CORS，生产环境应收敛为具体来源
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(questions.router)
app.include_router(exams.router)
app.include_router(agent.router)
app.include_router(stats.router)
app.include_router(admin.router)


@app.get("/health", tags=["health"])
def health():
    return {"status": "ok"}
