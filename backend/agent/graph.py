"""LangGraph ReAct Agent —— JLPT 学习辅导。

用 DeepSeek（OpenAI 兼容）作为 LLM，绑定 3 个工具（查题/组卷/语法讲解），
create_react_agent 驱动工具调用循环，MemorySaver 按 session_id 保存多轮对话记忆。
"""
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
- explain_grammar：识别语法/词汇讲解请求

行为准则：
1. 用户想做题/练习/模拟考时，调用 generate_exam 组卷，并清晰列出题目
2. 用户想看某类题目或需要例题时，调用 fetch_questions
3. 用户问语法点、词汇、题目为何选某项时，进行讲解，遵循以下结构：
   【答案解析】…
   【错项分析】a选项…，b选项…
4. 讲解一律用中文，简洁清晰，指出涉及的语法点
5. 展示题目时格式统一、美观，选项用 A/B/C/D 标注
6. 不要编造题目；题目一律来自工具返回的真实题库数据
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
