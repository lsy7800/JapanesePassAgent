"""LangGraph ReAct Agent —— JLPT 学习辅导。

用 DeepSeek（OpenAI 兼容）作为 LLM，绑定工具集，
create_react_agent 驱动工具调用循环，MemorySaver 按 session_id 保存多轮对话记忆。

提供两种运行模式：
- run_agent()       同步调用，返回完整回复
- stream_agent()    异步生成器，逐 token/事件 yield，供 SSE 端点使用
"""
import json
from typing import AsyncGenerator

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent

from crawler.config import DEEPSEEK_BASE_URL, DEEPSEEK_MODEL, require
from backend.agent.tools import ALL_TOOLS

SYSTEM_PROMPT = """你是一位专业的日语能力考试（JLPT）辅导专家，熟悉 N1~N5 各级别考纲。

你可以使用以下工具：
- fetch_questions：从题库检索真题，用于举例、讲解或组织练习
- generate_exam：为用户智能组卷生成一套练习试卷
- explain_grammar：对指定语法点或词汇生成结构化讲解（用法/例句/易错点/考点）
- answer_judge：对用户的具体作答进行 AI 判断和个性化解析
- analyze_weak_points：分析已提交试卷的错题，汇总薄弱知识点并给出学习建议

行为准则：
1. 用户想做题/练习/模拟考时，调用 generate_exam 组卷，清晰列出题目和选项
2. 用户想看某类题目或需要例题时，调用 fetch_questions
3. 用户问语法点或词汇用法时，调用 explain_grammar 生成结构化讲解
4. 用户提交了某题的作答、想知道对错原因时，调用 answer_judge
5. 用户完成考试后想了解薄弱点时，调用 analyze_weak_points（需提供 exam_id）
6. 讲解一律用中文，简洁清晰，展示题目时选项用 A/B/C/D 标注
7. 不要编造题目；题目一律来自工具返回的真实题库数据
"""


def _build_agent():
    llm = ChatOpenAI(
        model=DEEPSEEK_MODEL,
        base_url=DEEPSEEK_BASE_URL,
        api_key=require("DEEPSEEK_API_KEY"),
        temperature=0.3,
    )
    return create_react_agent(
        llm,
        ALL_TOOLS,
        prompt=SystemMessage(content=SYSTEM_PROMPT),
        checkpointer=MemorySaver(),
    )


# 进程内单例（MemorySaver 保存各 session 的对话历史）
_agent = None


def get_agent():
    global _agent
    if _agent is None:
        _agent = _build_agent()
    return _agent


async def stream_agent(
    message: str, session_id: str, context: dict | None = None
) -> AsyncGenerator[str, None]:
    """异步生成器，逐步 yield SSE 格式字符串。

    事件类型：
    - data: {"type": "token",   "content": "..."}   LLM 输出的文字片段
    - data: {"type": "tool",    "name": "...", "args": {...}}  工具调用开始
    - data: {"type": "done",    "session_id": "..."}  流结束
    - data: {"type": "error",   "detail": "..."}     异常
    """
    agent = get_agent()
    user_content = message
    if context:
        user_content = f"{message}\n\n（上下文：{context}）"

    config = {"configurable": {"thread_id": session_id}}
    inputs = {"messages": [HumanMessage(content=user_content)]}

    try:
        async for event in agent.astream_events(inputs, config=config, version="v2"):
            kind = event["event"]

            # LLM 文字 token
            if kind == "on_chat_model_stream":
                chunk = event["data"].get("chunk")
                if chunk and hasattr(chunk, "content") and chunk.content:
                    text = chunk.content if isinstance(chunk.content, str) else ""
                    if text:
                        yield f"data: {json.dumps({'type': 'token', 'content': text}, ensure_ascii=False)}\n\n"

            # 工具调用开始
            elif kind == "on_tool_start":
                tool_name = event.get("name", "")
                tool_input = event["data"].get("input", {})
                yield f"data: {json.dumps({'type': 'tool', 'name': tool_name, 'args': tool_input}, ensure_ascii=False)}\n\n"

    except Exception as e:
        yield f"data: {json.dumps({'type': 'error', 'detail': str(e)}, ensure_ascii=False)}\n\n"
    finally:
        yield f"data: {json.dumps({'type': 'done', 'session_id': session_id}, ensure_ascii=False)}\n\n"


def run_agent(message: str, session_id: str, context: dict | None = None) -> dict:
    """运行一轮对话，返回 {reply, tool_calls}。

    session_id 作为 langgraph thread_id，隔离并延续各会话的记忆。
    context（如 current_question_id）会作为附加提示拼进用户消息。
    """
    agent = get_agent()

    user_content = message
    if context:
        user_content = f"{message}\n\n（上下文：{context}）"

    result = agent.invoke(
        {"messages": [HumanMessage(content=user_content)]},
        config={"configurable": {"thread_id": session_id}},
    )

    messages = result["messages"]

    # 抽取本轮所有工具调用轨迹
    tool_calls = []
    for m in messages:
        for tc in getattr(m, "tool_calls", None) or []:
            tool_calls.append({"tool": tc.get("name", ""), "args": tc.get("args", {})})

    # 最后一条 AI 文本消息即最终回复
    reply = ""
    for m in reversed(messages):
        if m.__class__.__name__ == "AIMessage" and getattr(m, "content", ""):
            reply = m.content if isinstance(m.content, str) else str(m.content)
            break

    return {"reply": reply, "tool_calls": tool_calls}
