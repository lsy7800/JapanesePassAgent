"""Agent 工具集。

工具直接查数据库（复用 crawler.config.DB_CONFIG），不经 HTTP 自调用，避免服务自请求。
工具列表：
- fetch_questions      从题库按条件检索题目
- generate_exam        智能组卷并落库
- explain_grammar      调 LLM 生成结构化语法/词汇讲解
- answer_judge         给定题目+用户答案，AI 判断并解析
- analyze_weak_points  查指定试卷错题，汇总薄弱知识点
"""
import json

import pymysql
from pymysql.cursors import DictCursor
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

from crawler.config import DB_CONFIG, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL, require


def _connect():
    return pymysql.connect(cursorclass=DictCursor, **DB_CONFIG)


def _llm() -> ChatOpenAI:
    return ChatOpenAI(
        model=DEEPSEEK_MODEL,
        base_url=DEEPSEEK_BASE_URL,
        api_key=require("DEEPSEEK_API_KEY"),
        temperature=0.4,
    )


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
    user_id: int | None = None,
) -> dict:
    """智能组卷：按条件随机抽题生成一套试卷并落库，返回试卷ID与题目列表（不含答案）。

    参数：
    - level: 级别 N1~N5
    - total_questions: 题目数，默认 10，最多 50
    - difficulty_min/difficulty_max: 难度区间 0-9
    - user_id: 当前用户ID（由 Agent 调用方注入，用于关联考试历史）

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
                "INSERT INTO exams (user_id, level, total, time_limit, status) VALUES (%s, %s, %s, 0, 'created')",
                (user_id, level or "", len(group_ids)),
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
    """调用 AI 对指定语法点或词汇进行结构化讲解。

    参数：
    - topic: 语法点、词汇或问题描述（如「ば和たら的区别」「て形用法」）

    返回包含【用法说明】【例句】【易错点】【JLPT 考点】四个板块的讲解文本。
    """
    prompt = f"""你是 JLPT 考试专家，请对以下语法点/词汇进行结构化中文讲解：

主题：{topic}

请严格按以下格式输出，不要添加其他内容：

【用法说明】
（核心语法规则，2-4句）

【例句】
（2-3个由浅入深的例句，每句附中文翻译）

【易错点】
（考试中常见的混淆点或误用）

【JLPT 考点】
（本语法点在 N1~N5 哪个级别出现、常见题型）
"""
    llm = _llm()
    response = llm.invoke(prompt)
    return response.content


@tool
def answer_judge(
    question_content: str,
    options: dict,
    correct_answer: str,
    user_answer: str,
    analysis: str | None = None,
) -> str:
    """对用户的作答进行 AI 判断和个性化解析。

    参数：
    - question_content: 题干文本
    - options: 选项字典，如 {"a": "...", "b": "...", "c": "...", "d": "..."}
    - correct_answer: 正确答案标签（a/b/c/d）
    - user_answer: 用户选择的答案标签（a/b/c/d）
    - analysis: 题目原有解析（可选，作为补充参考）

    返回包含判断结果、错误原因分析和记忆建议的文本。
    """
    is_correct = user_answer.lower() == correct_answer.lower()
    verdict = "✓ 回答正确！" if is_correct else f"✗ 回答错误（你选了 {user_answer.upper()}，正确答案是 {correct_answer.upper()}）"

    opts_text = "\n".join(f"  {k.upper()}. {v}" for k, v in sorted(options.items()))
    ref_analysis = f"\n\n【原题解析参考】\n{analysis}" if analysis else ""

    prompt = f"""你是 JLPT 考试辅导老师，请对以下题目的作答给出详细点评。

题目：{question_content}
选项：
{opts_text}
正确答案：{correct_answer.upper()}
学生答案：{user_answer.upper()}
判断：{verdict}{ref_analysis}

请按以下格式输出点评，语言简洁，重点突出：

【判断】
{verdict}

【分析】
（解释正确答案为何正确，重点说明涉及的语法/词汇知识点）

【错误原因】
（{"本题回答正确，说明掌握了该知识点。" if is_correct else f"解释为何 {user_answer.upper()} 是错误的，避免类似误区"}）

【记忆技巧】
（一句话概括该考点的记忆方法）
"""
    llm = _llm()
    response = llm.invoke(prompt)
    return response.content


@tool
def analyze_weak_points(exam_id: int) -> dict:
    """分析指定试卷的错题，汇总薄弱知识点并给出学习建议。

    参数：
    - exam_id: 已提交的试卷 ID（status=submitted）

    返回 {summary, weak_points, suggestions}：
    - summary: 本次考试概况文字
    - weak_points: 薄弱知识点列表，每项含 point（知识点）和 wrong_count（错误次数）
    - suggestions: AI 给出的针对性学习建议
    """
    conn = _connect()
    try:
        with conn.cursor() as cur:
            # 检查试卷状态
            cur.execute("SELECT id, level, total, score, status FROM exams WHERE id = %s", (exam_id,))
            exam = cur.fetchone()
            if not exam:
                return {"error": f"试卷 {exam_id} 不存在"}
            if exam["status"] != "submitted":
                return {"error": f"试卷 {exam_id} 尚未提交，无法分析"}

            # 查所有错题的知识点
            cur.execute(
                """SELECT ei.group_id, qg.knowledge_points, qg.level, qg.difficulty
                   FROM exam_items ei
                   JOIN question_groups qg ON ei.group_id = qg.id
                   WHERE ei.exam_id = %s AND ei.is_correct = 0""",
                (exam_id,),
            )
            wrong_items = cur.fetchall()
    finally:
        conn.close()

    # 聚合薄弱知识点
    kp_counter: dict[str, int] = {}
    for item in wrong_items:
        for kp in _parse_kp(item["knowledge_points"]):
            kp_counter[kp] = kp_counter.get(kp, 0) + 1

    weak_points = sorted(
        [{"point": k, "wrong_count": v} for k, v in kp_counter.items()],
        key=lambda x: -x["wrong_count"],
    )

    total = exam["total"] or 1
    score = exam["score"] or 0
    accuracy = round(score / total * 100)
    wrong_count = total - score

    summary = (
        f"本次 {exam['level'] or '综合'} 级别试卷共 {total} 题，"
        f"答对 {score} 题，答错 {wrong_count} 题，正确率 {accuracy}%。"
    )

    if not weak_points:
        return {
            "summary": summary,
            "weak_points": [],
            "suggestions": "本次全部答对，保持良好状态！建议适当提升难度继续练习。",
        }

    # 调 LLM 生成学习建议
    top_points = "、".join(p["point"] for p in weak_points[:5])
    prompt = f"""JLPT 学生在一次考试中暴露了以下薄弱知识点（按错误频次排序）：{top_points}

考试概况：{summary}

请给出简洁、针对性的学习建议（3-5条，每条一行，以「•」开头），帮助学生在这些知识点上快速提升。
只输出建议列表，不要其他内容。"""

    llm = _llm()
    response = llm.invoke(prompt)

    return {
        "summary": summary,
        "weak_points": weak_points,
        "suggestions": response.content,
    }


@tool
def recommend_questions(
    weak_points: list[str],
    level: str | None = None,
    limit: int = 5,
) -> list[dict]:
    """根据薄弱知识点推荐针对性练习题。

    参数：
    - weak_points: 薄弱知识点列表（如 ["条件表达", "动词读音"]）
    - level: 限定级别 N1~N5，不传则不限
    - limit: 推荐题数，默认 5，最多 20

    返回题目列表，每题含题干、选项、正确答案、解析、知识点。
    """
    limit = max(1, min(limit, 20))
    if not weak_points:
        return []

    conn = _connect()
    try:
        with conn.cursor() as cur:
            # 用 JSON_OVERLAPS 找包含任意薄弱点的题组
            kp_json = json.dumps(weak_points, ensure_ascii=False)
            where = ["JSON_OVERLAPS(qg.knowledge_points, %s)"]
            params: list = [kp_json]
            if level:
                where.append("qg.level = %s")
                params.append(level)
            where_sql = "WHERE " + " AND ".join(where)
            cur.execute(
                f"""SELECT qg.id, qg.level, qg.difficulty, qg.knowledge_points
                    FROM question_groups qg {where_sql}
                    ORDER BY RAND() LIMIT %s""",
                params + [limit],
            )
            groups = cur.fetchall()
            result = []
            for g in groups:
                cur.execute(
                    "SELECT id, content, answer, analysis FROM questions WHERE group_id = %s ORDER BY seq LIMIT 1",
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
                    "options": options,
                    "answer": q["answer"],
                    "analysis": q["analysis"],
                })
        return result
    finally:
        conn.close()


ALL_TOOLS = [
    fetch_questions,
    generate_exam,
    explain_grammar,
    answer_judge,
    analyze_weak_points,
    recommend_questions,
]
