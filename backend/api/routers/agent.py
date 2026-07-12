"""Agent 对话接口。

POST /api/v1/agent/chat —— 同步与 Agent 对话（问答、讲解、组卷）。
会话记忆由 langgraph MemorySaver 按 session_id 维护。
"""
import uuid

from fastapi import APIRouter, HTTPException

from backend.schemas.agent import ChatRequest, ChatResponse, ToolCall

router = APIRouter(prefix="/api/v1/agent", tags=["agent"])


@router.post("/chat", response_model=ChatResponse)
def chat(payload: ChatRequest):
    session_id = payload.session_id or uuid.uuid4().hex

    # 延迟导入：避免应用启动阶段就初始化 LLM（无 key 时也能起服务）
    from backend.agent.graph import run_agent

    try:
        result = run_agent(payload.message, session_id, payload.context)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent 处理失败：{e}")

    return ChatResponse(
        reply=result["reply"],
        session_id=session_id,
        tool_calls=[ToolCall(**tc) for tc in result["tool_calls"]],
    )
