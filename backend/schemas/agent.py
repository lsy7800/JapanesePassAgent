"""Agent 对话接口的 Pydantic 模型（README「Agent 对话」）。"""
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, description="用户消息")
    session_id: str | None = Field(default=None, description="会话ID，不传则新建")
    context: dict | None = Field(default=None, description="附加上下文，如 {current_question_id: 42}")


class ToolCall(BaseModel):
    tool: str
    args: dict = Field(default_factory=dict)


class ChatResponse(BaseModel):
    reply: str
    session_id: str
    tool_calls: list[ToolCall] = Field(default_factory=list)
