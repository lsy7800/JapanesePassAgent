"""Agent 工具集。

工具直接查数据库（复用 crawler.config.DB_CONFIG），不经 HTTP 自调用，避免服务自请求。
对应 README「Agent Tools」中的核心 3 个：
- QuestionFetcher  -> fetch_questions
- ExamGenerator    -> generate_exam
- GrammarExplainer -> explain_grammar（无 DB，主要靠 system prompt 约束讲解格式）
"""
import json

import pymysql
from pymysql.cursors import DictCursor
from langchain_core.tools import tool

from crawler.config import DB_CONFIG


def _connect():
    return pymysql.connect(cursorclass=DictCursor, **DB_CONFIG)


def _parse_kp(raw):
    if raw is None or raw == "":
        return []
    if isinstance(raw, list):
        return raw
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []


@tool
def fetch_questions(
    level: str | None = None,
    type: str | None = None,
    difficulty_min: int | None = None,
    difficulty_max: int | None = None,
    knowledge_point: str | None = None,
    limit: int = 5,
) -> list[dict]:
    """从题库检索题目，用于讲解、举例或组织练习。

    参数：
    - level: 级别 N1~N5
    - type: 题型 single_choice/cloze/reading
    - difficulty_min/difficulty_max: 难度区间 0-9
    - knowledge_point: 知识点关键词（如「条件表达」）
    - limit: 返回题数，默认 5，最多 20

    返回题目列表，每题含题干、选项、正确答案、解析、难度、知识点。
    """
    limit = max(1, min(limit, 20))
    where, params = [], []
    if level:
        where.append("qg.level = %s")
        params.append(level)
    if type:
        where.append("qg.type = %s")
        params.append(type)
    if difficulty_min is not None:
        where.append("qg.difficulty >= %s")
        params.append(difficulty_min)
    if difficulty_max is not None:
        where.append("qg.difficulty <= %s")
        params.append(difficulty_max)
    if knowledge_point:
        where.append("JSON_CONTAINS(qg.knowledge_points, %s)")
        params.append(json.dumps(knowledge_point, ensure_ascii=False))
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""

    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""SELECT qg.id, qg.type, qg.level, qg.difficulty, qg.knowledge_points
                    FROM question_groups qg {where_sql}
                    ORDER BY RAND() LIMIT %s""",
                params + [limit],
            )
            groups = cur.fetchall()
            result = []
            for g in groups:
                cur.execute(
                    "SELECT id, content, marked, answer, analysis FROM questions WHERE group_id = %s ORDER BY seq LIMIT 1",
                    (g["id"],),
                )
                q = cur.fetchone()
                if not q:
                    continue
                cur.execute(
                    "SELECT label, content FROM options WHERE question_id = %s ORDER BY label",
                    (q["id"],),
                )
                options = {o["label"]: o["content"] for o in cur.fetchall()}
                result.append({
                    "group_id": g["id"],
                    "level": g["level"],
                    "difficulty": g["difficulty"],
                    "knowledge_points": _parse_kp(g["knowledge_points"]),
                    "content": q["content"],
                    "marked": q["marked"],
                    "options": options,
                    "answer": q["answer"],
                    "analysis": q["analysis"],
                })
        return result
    finally:
        conn.close()


@tool
def generate_exam(
    level: str | None = None,
    total_questions: int = 10,
    difficulty_min: int | None = None,
    difficulty_max: int | None = None,
) -> dict:
    """智能组卷：按条件随机抽题生成一套试卷并落库，返回试卷ID与题目列表（不含答案）。

    参数：
    - level: 级别 N1~N5
    - total_questions: 题目数，默认 10，最多 50
    - difficulty_min/difficulty_max: 难度区间 0-9

    返回 {exam_id, total, items}，items 每题含 seq、题干、选项（不含答案）。
    用户做完后可通过 exam_id 提交判分。
    """
    total_questions = max(1, min(total_questions, 50))
    where, params = [], []
    if level:
        where.append("level = %s")
        params.append(level)
    if difficulty_min is not None:
        where.append("difficulty >= %s")
        params.append(difficulty_min)
    if difficulty_max is not None:
        where.append("difficulty <= %s")
        params.append(difficulty_max)
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""

    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT id FROM question_groups {where_sql} ORDER BY RAND() LIMIT %s",
                params + [total_questions],
            )
            group_ids = [r["id"] for r in cur.fetchall()]
            if not group_ids:
                return {"exam_id": None, "total": 0, "items": [], "message": "没有符合条件的题目"}

            cur.execute(
                "INSERT INTO exams (level, total, time_limit, status) VALUES (%s, %s, 0, 'created')",
                (level or "", len(group_ids)),
            )
            exam_id = cur.lastrowid

            items = []
            for seq, gid in enumerate(group_ids, start=1):
                cur.execute(
                    "INSERT INTO exam_items (exam_id, seq, group_id) VALUES (%s, %s, %s)",
                    (exam_id, seq, gid),
                )
                cur.execute(
                    "SELECT id, content FROM questions WHERE group_id = %s ORDER BY seq LIMIT 1",
                    (gid,),
                )
                q = cur.fetchone()
                options = {}
                if q:
                    cur.execute(
                        "SELECT label, content FROM options WHERE question_id = %s ORDER BY label",
                        (q["id"],),
                    )
                    options = {o["label"]: o["content"] for o in cur.fetchall()}
                items.append({
                    "seq": seq,
                    "content": q["content"] if q else None,
                    "options": options,
                })
        conn.commit()
        return {"exam_id": exam_id, "total": len(group_ids), "items": items}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@tool
def explain_grammar(topic: str) -> str:
    """标记需要进行语法/词汇讲解的主题。

    参数 topic：语法点名称或题目相关问题（如「ば和たら的区别」）。

    该工具本身不产生讲解内容——讲解由你（Agent）依据 JLPT 考纲知识，
    遵循「答案解析 + 错项分析」的结构，用中文简洁清晰地完成。
    调用此工具表示你已识别出这是一个讲解请求，随后请直接给出讲解。
    """
    return f"已识别讲解请求：{topic}。请依据 JLPT 考纲给出结构化中文讲解。"


ALL_TOOLS = [fetch_questions, generate_exam, explain_grammar]
