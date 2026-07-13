"""LangGraph ReAct Agent —— JLPT 学习辅导。

用 DeepSeek（OpenAI 兼容）作为 LLM，绑定工具集，create_react_agent 驱动工具调用循环。

对话记忆持久化在 MySQL（chat_sessions / chat_messages），每轮：
1. 读取该会话的历史消息，拼成 [system] + 历史 + 本轮消息
2. 运行 Agent
3. 把用户消息与 AI 回复落库
不再使用进程内 MemorySaver，重启/刷新均不丢上下文。

提供两种运行模式：
- run_agent()       同步调用，返回完整回复
- stream_agent()    异步生成器，逐 token/事件 yield，供 SSE 端点使用
"""
import json
from typing import AsyncGenerator

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from crawler.config import DEEPSEEK_BASE_URL, DEEPSEEK_MODEL, require
from backend.agent.tools import ALL_TOOLS
from backend.db import chat_repo

SYSTEM_PROMPT = """你是一位专业的日语能力考试（JLPT）辅导专家，熟悉 N1~N5 各级别考纲。

你可以使用以下工具：
- fetch_questions：从题库检索真题，用于举例、讲解或组织练习
- generate_exam：为用户智能组卷生成一套练习试卷（调用时必须传入 user_id 参数）
- explain_grammar：对指定语法点或词汇生成结构化讲解（用法/例句/易错点/考点）
- answer_judge：对用户的具体作答进行 AI 判断和个性化解析
- analyze_weak_points：分析已提交试卷的错题，汇总薄弱知识点并给出学习建议
- recommend_questions：根据薄弱知识点推荐针对性练习题
- export_exam：把已生成的试卷导出为可下载的 Markdown 文件（用户说导出/下载/打印/写入 markdown 时用）

行为准则：
1. 用户想做题/练习/模拟考时，调用 generate_exam 组卷，清晰列出题目和选项
2. 调用 generate_exam 时，始终将系统提示中提供的 user_id 作为参数传入
   - 用户要「多个题型各 N 道」（如「汉字读音和前后关系各十道」）时，必须用 category_quotas
     一次性组成【一张】试卷，例如 category_quotas={"kanji_reading":10,"context":10}；
     绝不要为每个题型分别调用 generate_exam（那会拆成多张卷、多份文件）
3. 用户想看某类题目或需要例题时，调用 fetch_questions
4. 用户问语法点或词汇用法时，调用 explain_grammar 生成结构化讲解
5. 用户提交了某题的作答、想知道对错原因时，调用 answer_judge
6. 用户完成考试后想了解薄弱点时，调用 analyze_weak_points（需提供 exam_id）
7. 用户想针对薄弱知识点练习时，调用 recommend_questions 推荐题目
8. 用户想把试卷导出/下载/打印/写入文件时，调用 export_exam（需先有 generate_exam 返回的 exam_id）；
   调用后前端会自动显示下载按钮，你只需简短告知用户点击下载即可，不要在回复里粘贴整份文件内容
9. 讲解一律用中文，简洁清晰，展示题目时选项用 A/B/C/D 标注
10. 不要编造题目；题目一律来自工具返回的真实题库数据
"""


def _build_prompt(user_id: int | None) -> SystemMessage:
    extra = f"\n\n当前用户 user_id = {user_id}，调用 generate_exam 时必须传入此值。" if user_id else ""
    return SystemMessage(content=SYSTEM_PROMPT + extra)


def _history_to_messages(rows: list[dict]) -> list:
    """把 chat_messages 行转成 LangChain 消息对象。"""
    out = []
    for r in rows:
        if r["role"] == "user":
            out.append(HumanMessage(content=r["content"]))
        elif r["role"] == "assistant":
            out.append(AIMessage(content=r["content"]))
    return out


def _build_agent():
    llm = ChatOpenAI(
        model=DEEPSEEK_MODEL,
        base_url=DEEPSEEK_BASE_URL,
        api_key=require("DEEPSEEK_API_KEY"),
        temperature=0.3,
    )
    return create_react_agent(llm, ALL_TOOLS)


# 进程内单例（无状态，仅缓存 LLM/工具绑定，避免重复构建）
_agent = None


def get_agent():
    global _agent
    if _agent is None:
        _agent = _build_agent()
    return _agent


def _prepare_turn(message: str, session_id: int | None, user_id: int | None) -> tuple[int, list]:
    """流式/同步前的准备：确保会话存在、读历史、落库用户消息。

    返回 (session_id, 历史消息对象列表)。用短连接，避免占用连接跨越 LLM 调用。
    """
    with chat_repo.open_conn() as conn:
        with conn.cursor() as cur:
            if session_id:
                # 归属校验；不属于该用户则视作新建，避免越权写入他人会话
                if user_id and not chat_repo.owns_session(cur, session_id, user_id):
                    session_id = chat_repo.create_session(cur, user_id, first_message=message)
                    history_rows = []
                else:
                    history_rows = chat_repo.load_history(cur, session_id)
            else:
                session_id = chat_repo.create_session(cur, user_id, first_message=message)
                history_rows = []
            chat_repo.append_message(cur, session_id, "user", message)
    return session_id, _history_to_messages(history_rows)


def _save_reply(session_id: int, reply: str) -> None:
    """落库 AI 回复（非空才存）。"""
    if not reply:
        return
    with chat_repo.open_conn() as conn:
        with conn.cursor() as cur:
            chat_repo.append_message(cur, session_id, "assistant", reply)


async def stream_agent(
    message: str, session_id: int | None = None, context: dict | None = None, user_id: int | None = None
) -> AsyncGenerator[str, None]:
    """异步生成器，逐步 yield SSE 格式字符串。"""
    agent = get_agent()

    session_id, history = _prepare_turn(message, session_id, user_id)
    # 先把 session_id 告知前端，便于其立即持久化（即使后续流出错也已拿到）
    yield f"data: {json.dumps({'type': 'session', 'session_id': session_id}, ensure_ascii=False)}\n\n"

    user_content = message
    if context:
        user_content = f"{message}\n\n（上下文：{context}）"

    inputs = {
        "messages": [
            _build_prompt(user_id),
            *history,
            HumanMessage(content=user_content),
        ]
    }

    reply_parts: list[str] = []
    try:
        async for event in agent.astream_events(inputs, version="v2"):
            kind = event["event"]

            if kind == "on_chat_model_stream":
                chunk = event["data"].get("chunk")
                if chunk and hasattr(chunk, "content") and chunk.content:
                    text = chunk.content if isinstance(chunk.content, str) else ""
                    if text:
                        reply_parts.append(text)
                        yield f"data: {json.dumps({'type': 'token', 'content': text}, ensure_ascii=False)}\n\n"

            elif kind == "on_tool_start":
                tool_name = event.get("name", "")
                tool_input = event["data"].get("input", {})
                yield f"data: {json.dumps({'type': 'tool', 'name': tool_name, 'args': tool_input}, ensure_ascii=False)}\n\n"

    except Exception as e:
        yield f"data: {json.dumps({'type': 'error', 'detail': str(e)}, ensure_ascii=False)}\n\n"
    finally:
        # 无论正常结束还是中途出错，已产出的回复都尽量落库
        _save_reply(session_id, "".join(reply_parts))
        yield f"data: {json.dumps({'type': 'done', 'session_id': session_id}, ensure_ascii=False)}\n\n"


def run_agent(message: str, session_id: int | None = None, context: dict | None = None, user_id: int | None = None) -> dict:
    """运行一轮对话，返回 {reply, session_id, tool_calls}。"""
    agent = get_agent()

    session_id, history = _prepare_turn(message, session_id, user_id)

    user_content = message
    if context:
        user_content = f"{message}\n\n（上下文：{context}）"

    result = agent.invoke(
        {
            "messages": [
                _build_prompt(user_id),
                *history,
                HumanMessage(content=user_content),
            ]
        }
    )

    messages = result["messages"]

    tool_calls = []
    for m in messages:
        for tc in getattr(m, "tool_calls", None) or []:
            tool_calls.append({"tool": tc.get("name", ""), "args": tc.get("args", {})})

    reply = ""
    for m in reversed(messages):
        if m.__class__.__name__ == "AIMessage" and getattr(m, "content", ""):
            reply = m.content if isinstance(m.content, str) else str(m.content)
            break

    _save_reply(session_id, reply)

    return {"reply": reply, "session_id": session_id, "tool_calls": tool_calls}

