"""Agent 对话接口。

POST /api/v1/agent/chat    同步接口（保留，兼容旧调用）
GET  /api/v1/agent/stream  SSE 流式接口，参数通过 query string 传递

SSE 端点使用 token query 参数认证（EventSource 不支持自定义请求头）。
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from jose import JWTError

from backend.api.deps import get_current_user, get_db
from backend.schemas.agent import ChatRequest, ChatResponse, ToolCall
from backend.utils.security import decode_token

router = APIRouter(prefix="/api/v1/agent", tags=["agent"])


def _auth_by_token(token: str, conn) -> int:
    """SSE 专用：从 query param token 解析用户，返回 user_id，失败抛 HTTPException。"""
    if not token:
        raise HTTPException(status_code=401, detail="未登录")
    try:
        payload = decode_token(token)
    except JWTError:
        raise HTTPException(status_code=401, detail="Token 无效或已过期")
    user_id = int(payload["sub"])
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM users WHERE id = %s", (user_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=401, detail="用户不存在")
    return user_id


@router.post("/chat", response_model=ChatResponse)
def chat(payload: ChatRequest, current_user=Depends(get_current_user)):
    from backend.agent.graph import run_agent
    try:
        result = run_agent(
            payload.message, payload.session_id, payload.context, user_id=current_user["id"]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent 处理失败：{e}")
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
    user_id = _auth_by_token(token, conn)
    from backend.agent.graph import stream_agent

    return StreamingResponse(
        stream_agent(message, session_id, user_id=user_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
