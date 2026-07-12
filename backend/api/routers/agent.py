"""Agent 对话接口。

POST /api/v1/agent/chat    同步接口（保留，兼容旧调用）
GET  /api/v1/agent/stream  SSE 流式接口，参数通过 query string 传递
"""
import uuid

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from backend.schemas.agent import ChatRequest, ChatResponse, ToolCall

router = APIRouter(prefix="/api/v1/agent", tags=["agent"])


@router.post("/chat", response_model=ChatResponse)
def chat(payload: ChatRequest):
    session_id = payload.session_id or uuid.uuid4().hex
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


@router.get("/stream")
async def stream(
    message: str = Query(..., description="用户消息"),
    session_id: str = Query(default=None, description="会话ID，不传则新建"),
):
    """SSE 流式对话接口。

    前端用 EventSource 连接，每条 SSE 数据格式：
      data: {"type": "token",  "content": "..."}
      data: {"type": "tool",   "name": "...", "args": {...}}
      data: {"type": "done",   "session_id": "..."}
      data: {"type": "error",  "detail": "..."}
    """
    sid = session_id or uuid.uuid4().hex
    from backend.agent.graph import stream_agent

    return StreamingResponse(
        stream_agent(message, sid),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # 禁用 nginx 缓冲，确保逐块推送
        },
    )
