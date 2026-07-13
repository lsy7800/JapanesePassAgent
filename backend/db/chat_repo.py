"""对话会话与消息的持久化仓储。

设计：
- 函数统一接收 pymysql cursor（DictCursor），由调用方管理连接/事务：
  - 路由层复用请求连接（get_db 依赖）
  - graph.py 在请求上下文之外，用 open_conn() 自开连接
- 归属校验：涉及具体会话的读写均校验 user_id，防越权。
"""
from contextlib import contextmanager

import pymysql
from pymysql.cursors import DictCursor

from crawler.config import DB_CONFIG

# 拼接历史时默认回溯的消息条数（user+assistant 合计），避免上下文无限增长
DEFAULT_HISTORY_LIMIT = 20


@contextmanager
def open_conn():
    """在请求上下文之外使用（如 graph.py）。自动提交/回滚并关闭。"""
    conn = pymysql.connect(cursorclass=DictCursor, **DB_CONFIG)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _title_from(text: str) -> str:
    """取首条用户消息前若干字作为会话标题。"""
    t = (text or "").strip().replace("\n", " ")
    return (t[:20] or "新对话")


def create_session(cur, user_id: int, first_message: str | None = None) -> int:
    """创建会话，返回 session_id。标题取首条消息前 20 字。"""
    title = _title_from(first_message) if first_message else "新对话"
    cur.execute(
        "INSERT INTO chat_sessions (user_id, title) VALUES (%s, %s)",
        (user_id, title),
    )
    return cur.lastrowid


def owns_session(cur, session_id: int, user_id: int) -> bool:
    cur.execute(
        "SELECT 1 FROM chat_sessions WHERE id = %s AND user_id = %s",
        (session_id, user_id),
    )
    return cur.fetchone() is not None


def append_message(cur, session_id: int, role: str, content: str) -> None:
    """追加一条消息并刷新会话 updated_at。role: 'user' | 'assistant'。"""
    cur.execute(
        "INSERT INTO chat_messages (session_id, role, content) VALUES (%s, %s, %s)",
        (session_id, role, content),
    )
    cur.execute(
        "UPDATE chat_sessions SET updated_at = CURRENT_TIMESTAMP WHERE id = %s",
        (session_id,),
    )


def load_history(cur, session_id: int, limit: int = DEFAULT_HISTORY_LIMIT) -> list[dict]:
    """读取最近 limit 条消息，按时间升序返回 [{role, content}, ...]。"""
    cur.execute(
        """SELECT role, content FROM chat_messages
           WHERE session_id = %s ORDER BY id DESC LIMIT %s""",
        (session_id, limit),
    )
    rows = cur.fetchall()
    rows.reverse()  # 取最近 N 条后再转回升序
    return rows


def list_sessions(cur, user_id: int) -> list[dict]:
    """当前用户的会话列表，按最近更新降序。"""
    cur.execute(
        """SELECT id, title, created_at, updated_at
           FROM chat_sessions WHERE user_id = %s
           ORDER BY updated_at DESC""",
        (user_id,),
    )
    return cur.fetchall()


def get_messages(cur, session_id: int, user_id: int) -> list[dict] | None:
    """会话的全部消息（带归属校验）。不属于该用户返回 None。"""
    if not owns_session(cur, session_id, user_id):
        return None
    cur.execute(
        """SELECT id, role, content, created_at FROM chat_messages
           WHERE session_id = %s ORDER BY id""",
        (session_id,),
    )
    return cur.fetchall()


def rename_session(cur, session_id: int, user_id: int, title: str) -> bool:
    cur.execute(
        "UPDATE chat_sessions SET title = %s WHERE id = %s AND user_id = %s",
        (title.strip()[:120] or "新对话", session_id, user_id),
    )
    return cur.rowcount > 0


def delete_session(cur, session_id: int, user_id: int) -> bool:
    """删除会话（消息由外键 CASCADE 一并删除）。"""
    cur.execute(
        "DELETE FROM chat_sessions WHERE id = %s AND user_id = %s",
        (session_id, user_id),
    )
    return cur.rowcount > 0
