"""Agent 对话接口。

POST /api/v1/agent/chat    同步接口（保留，兼容旧调用）
GET  /api/v1/agent/stream  SSE 流式接口，参数通过 query string 传递

SSE 端点使用 token query 参数认证（EventSource 不支持自定义请求头）。
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from backend.api.deps import auth_by_query_token, get_current_user, get_db
from backend.schemas.agent import ChatRequest, ChatResponse, ToolCall
from backend.utils.logging_config import get_logger
from backend.utils.ratelimit import limit_llm_by_user

router = APIRouter(prefix="/api/v1/agent", tags=["agent"])

logger = get_logger("backend.agent")


@router.post("/chat", response_model=ChatResponse)
def chat(payload: ChatRequest, request: Request, current_user=Depends(get_current_user)):
    from backend.agent.graph import run_agent

    limit_llm_by_user(current_user["id"])
    try:
        result = run_agent(
            payload.message, payload.session_id, payload.context, user_id=current_user["id"]
        )
    except Exception:
        # 之前这里 detail=f"Agent 处理失败：{e}" 会把 DB 连接信息或上游 API
        # 报错体带给客户端，服务端反而不留痕。现在反过来：堆栈进日志，
        # 客户端只拿 request_id。
        request_id = getattr(request.state, "request_id", None)
        logger.exception(
            "Agent 同步对话失败",
            extra={"user_id": current_user["id"], "request_id": request_id},
        )
        raise HTTPException(
            status_code=500,
            detail=f"Agent 处理失败，请联系管理员并提供 request_id: {request_id}",
        )
    return ChatResponse(
        reply=result["reply"],
        session_id=result["session_id"],
        tool_calls=[ToolCall(**tc) for tc in result["tool_calls"]],
    )


@router.get("/stream")
async def stream(
    message: str = Query(..., description="用户消息"),
    session_id: int | None = Query(default=None, description="会话ID，不传则新建"),
    token: str = Query(default="", description="JWT access_token（EventSource 不支持 Header，走 query）"),
    conn=Depends(get_db),
):
    """SSE 流式对话接口。"""
    user_id = auth_by_query_token(token, conn)
    # 限流放在认证之后：先确认身份才能按用户计数
    limit_llm_by_user(user_id)
    from backend.agent.graph import stream_agent

    return StreamingResponse(
        stream_agent(message, session_id, user_id=user_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
