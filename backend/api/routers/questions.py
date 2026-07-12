"""题库读接口。

对应 README「API 设计 - 题库管理」：
- GET /api/v1/questions           题目列表（分页 + 筛选）
- GET /api/v1/questions/{group_id} 获取完整题组（含所有子题和选项）
"""
import json

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.api.deps import get_db
from backend.schemas.question import (
    OptionOut,
    QuestionGroupOut,
    QuestionGroupSummary,
    QuestionListResponse,
    QuestionOut,
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


@router.get("/questions", response_model=QuestionListResponse)
def list_questions(
    type: str | None = Query(default=None, description="题型：single_choice/cloze/reading"),
    level: str | None = Query(default=None, description="级别：N1~N5"),
    difficulty_min: int | None = Query(default=None, ge=0, le=9),
    difficulty_max: int | None = Query(default=None, ge=0, le=9),
    knowledge_point: str | None = Query(default=None, description="知识点关键词"),
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

    where_sql = f"WHERE {' AND '.join(where)}" if where else ""

    with conn.cursor() as cursor:
        cursor.execute(f"SELECT COUNT(*) AS total FROM question_groups {where_sql}", params)
        total = cursor.fetchone()["total"]

        offset = (page - 1) * page_size
        cursor.execute(
            f"""SELECT id, type, level, exam_date, difficulty, knowledge_points
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
        )
        for r in rows
    ]
    return QuestionListResponse(items=items, page=page, page_size=page_size, total=total)


@router.get("/questions/{group_id}", response_model=QuestionGroupOut)
def get_question_group(group_id: int, conn=Depends(get_db)):
    with conn.cursor() as cursor:
        cursor.execute(
            """SELECT id, type, article, level, exam_date, difficulty, knowledge_points
               FROM question_groups WHERE id = %s""",
            (group_id,),
        )
        group = cursor.fetchone()
        if group is None:
            raise HTTPException(status_code=404, detail=f"题组 {group_id} 不存在")

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
