"""题库读接口。

对应 README「API 设计 - 题库管理」：
- GET /api/v1/questions           题目列表（分页 + 筛选）
- GET /api/v1/questions/{group_id} 获取完整题组（含所有子题和选项）
"""
import json

from fastapi import APIRouter, Depends, HTTPException, Query, status

from backend.api.deps import get_db
from backend.schemas.question import (
    OptionOut,
    QuestionGroupCreate,
    QuestionGroupOut,
    QuestionGroupSummary,
    QuestionListResponse,
    QuestionOut,
    SourceStat,
)

router = APIRouter(prefix="/api/v1", tags=["questions"])


def _parse_knowledge_points(raw) -> list:
    """knowledge_points 存为 JSON 列，DictCursor 取出可能是 str 或已解析的 list。"""
    if raw is None or raw == "":
        return []
    if isinstance(raw, list):
        return raw
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []


@router.get("/sources", response_model=list[SourceStat])
def list_sources(conn=Depends(get_db)):
    """列出各题库批次及其题组数，供前端批次筛选下拉使用。source 为 NULL 的（API 手动创建）归并为 'manual'。"""
    with conn.cursor() as cursor:
        cursor.execute(
            """SELECT COALESCE(source, 'manual') AS source, COUNT(*) AS count
               FROM question_groups
               GROUP BY COALESCE(source, 'manual')
               ORDER BY source"""
        )
        rows = cursor.fetchall()
    return [SourceStat(source=r["source"], count=r["count"]) for r in rows]


@router.get("/questions", response_model=QuestionListResponse)
def list_questions(
    type: str | None = Query(default=None, description="题型：single_choice/cloze/reading"),
    level: str | None = Query(default=None, description="级别：N1~N5"),
    difficulty_min: int | None = Query(default=None, ge=0, le=9),
    difficulty_max: int | None = Query(default=None, ge=0, le=9),
    knowledge_point: str | None = Query(default=None, description="知识点关键词"),
    source: str | None = Query(default=None, description="题库批次来源，如 result_67_validated"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    conn=Depends(get_db),
):
    where = []
    params = []
    if type:
        where.append("type = %s")
        params.append(type)
    if level:
        where.append("level = %s")
        params.append(level)
    if difficulty_min is not None:
        where.append("difficulty >= %s")
        params.append(difficulty_min)
    if difficulty_max is not None:
        where.append("difficulty <= %s")
        params.append(difficulty_max)
    if knowledge_point:
        where.append("JSON_CONTAINS(knowledge_points, %s)")
        params.append(json.dumps(knowledge_point, ensure_ascii=False))
    if source:
        where.append("source = %s")
        params.append(source)

    where_sql = f"WHERE {' AND '.join(where)}" if where else ""

    with conn.cursor() as cursor:
        cursor.execute(f"SELECT COUNT(*) AS total FROM question_groups {where_sql}", params)
        total = cursor.fetchone()["total"]

        offset = (page - 1) * page_size
        cursor.execute(
            f"""SELECT id, type, level, exam_date, difficulty, knowledge_points, source
                FROM question_groups {where_sql}
                ORDER BY id
                LIMIT %s OFFSET %s""",
            params + [page_size, offset],
        )
        rows = cursor.fetchall()

    items = [
        QuestionGroupSummary(
            id=r["id"],
            type=r["type"],
            level=r["level"] or "",
            exam_date=r["exam_date"] or "",
            difficulty=r["difficulty"] or 0,
            knowledge_points=_parse_knowledge_points(r["knowledge_points"]),
            source=r["source"],
        )
        for r in rows
    ]
    return QuestionListResponse(items=items, page=page, page_size=page_size, total=total)


def _fetch_group(cursor, group_id: int) -> QuestionGroupOut | None:
    """从三表组装完整题组；不存在返回 None。GET/POST/PUT 共用。"""
    cursor.execute(
        """SELECT id, type, article, level, exam_date, difficulty, knowledge_points
           FROM question_groups WHERE id = %s""",
        (group_id,),
    )
    group = cursor.fetchone()
    if group is None:
        return None

    cursor.execute(
        """SELECT id, seq, content, marked, answer, analysis
           FROM questions WHERE group_id = %s ORDER BY seq""",
        (group_id,),
    )
    questions = cursor.fetchall()

    question_out = []
    for q in questions:
        cursor.execute(
            "SELECT label, content FROM options WHERE question_id = %s ORDER BY label",
            (q["id"],),
        )
        options = [OptionOut(label=o["label"], content=o["content"]) for o in cursor.fetchall()]
        question_out.append(
            QuestionOut(
                seq=q["seq"],
                content=q["content"],
                marked=q["marked"] or "",
                answer=q["answer"],
                analysis=q["analysis"],
                options=options,
            )
        )

    return QuestionGroupOut(
        id=group["id"],
        type=group["type"],
        article=group["article"],
        level=group["level"] or "",
        exam_date=group["exam_date"] or "",
        difficulty=group["difficulty"] or 0,
        knowledge_points=_parse_knowledge_points(group["knowledge_points"]),
        questions=question_out,
    )


def _insert_children(cursor, group_id: int, questions) -> None:
    """为题组插入子题及各自的选项。POST 与 PUT 共用。"""
    for q in questions:
        cursor.execute(
            """INSERT INTO questions (group_id, seq, content, marked, answer, analysis)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (group_id, q.seq, q.content, q.marked, q.answer, q.analysis),
        )
        question_id = cursor.lastrowid
        for o in q.options:
            cursor.execute(
                "INSERT INTO options (question_id, label, content) VALUES (%s, %s, %s)",
                (question_id, o.label, o.content),
            )


def _insert_group_rows(cursor, payload: QuestionGroupCreate) -> int:
    """插入题组及其子题、选项，返回新 group_id。source/source_ref 留 NULL（手动创建）。"""
    cursor.execute(
        """INSERT INTO question_groups
           (type, article, level, exam_date, difficulty, knowledge_points, source, source_ref)
           VALUES (%s, %s, %s, %s, %s, %s, NULL, NULL)""",
        (
            payload.type,
            payload.article,
            payload.level,
            payload.exam_date,
            payload.difficulty,
            json.dumps(payload.knowledge_points, ensure_ascii=False),
        ),
    )
    group_id = cursor.lastrowid
    _insert_children(cursor, group_id, payload.questions)
    return group_id


@router.get("/questions/{group_id}", response_model=QuestionGroupOut)
def get_question_group(group_id: int, conn=Depends(get_db)):
    with conn.cursor() as cursor:
        group = _fetch_group(cursor, group_id)
    if group is None:
        raise HTTPException(status_code=404, detail=f"题组 {group_id} 不存在")
    return group


@router.post("/questions", response_model=QuestionGroupOut, status_code=status.HTTP_201_CREATED)
def create_question_group(payload: QuestionGroupCreate, conn=Depends(get_db)):
    try:
        with conn.cursor() as cursor:
            group_id = _insert_group_rows(cursor, payload)
            group = _fetch_group(cursor, group_id)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return group


@router.put("/questions/{group_id}", response_model=QuestionGroupOut)
def replace_question_group(group_id: int, payload: QuestionGroupCreate, conn=Depends(get_db)):
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM question_groups WHERE id = %s", (group_id,))
            if cursor.fetchone() is None:
                raise HTTPException(status_code=404, detail=f"题组 {group_id} 不存在")

            # 全量替换：更新题组行，删旧子题（外键级联清选项）后重建
            cursor.execute(
                """UPDATE question_groups
                   SET type=%s, article=%s, level=%s, exam_date=%s,
                       difficulty=%s, knowledge_points=%s
                   WHERE id=%s""",
                (
                    payload.type,
                    payload.article,
                    payload.level,
                    payload.exam_date,
                    payload.difficulty,
                    json.dumps(payload.knowledge_points, ensure_ascii=False),
                    group_id,
                ),
            )
            cursor.execute("DELETE FROM questions WHERE group_id = %s", (group_id,))
            _insert_children(cursor, group_id, payload.questions)
            group = _fetch_group(cursor, group_id)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return group


@router.delete("/questions/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_question_group(group_id: int, conn=Depends(get_db)):
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM question_groups WHERE id = %s", (group_id,))
            if cursor.rowcount == 0:
                raise HTTPException(status_code=404, detail=f"题组 {group_id} 不存在")
        conn.commit()
    except Exception:
        conn.rollback()
        raise

