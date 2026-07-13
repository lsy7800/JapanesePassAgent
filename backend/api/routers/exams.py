"""考试/组卷接口。

对应 README「API 设计 - 考试与做题」：
- POST /api/v1/exams/generate       智能组卷（随机选题，落库，返回不含答案的试卷）
- GET  /api/v1/exams/{exam_id}       获取试卷内容（不含答案）
- POST /api/v1/exams/{exam_id}/submit 提交答案并判分
- GET  /api/v1/exams/{exam_id}/result 获取结果（含正确答案与解析）

判分以题组为单位：当前题库均为单选题（1题组1子题），取题组首道子题的 answer 比对。
不调用 LLM，纯比对，结果确定。
"""
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Response, status

from backend.api.deps import get_db, get_current_user
from backend.api.exam_export import render_exam_markdown
from backend.schemas.exam import (
    ExamGenerateRequest,
    ExamHistoryResponse,
    ExamItemOut,
    ExamOptionOut,
    ExamOut,
    ExamResultOut,
    ExamSummary,
    ResultItemOut,
    SubmitRequest,
)

router = APIRouter(prefix="/api/v1/exams", tags=["exams"])


def _group_options(cursor, question_id: int) -> list[ExamOptionOut]:
    cursor.execute(
        "SELECT label, content FROM options WHERE question_id = %s ORDER BY label",
        (question_id,),
    )
    return [ExamOptionOut(label=o["label"], content=o["content"]) for o in cursor.fetchall()]


def _first_question(cursor, group_id: int):
    """取题组首道子题（含 answer/analysis/content）。当前均单选题，一组一题。"""
    cursor.execute(
        """SELECT id, content, marked, answer, analysis
           FROM questions WHERE group_id = %s ORDER BY seq LIMIT 1""",
        (group_id,),
    )
    return cursor.fetchone()


@router.get("", response_model=ExamHistoryResponse)
def list_exams(
    page: int = 1,
    page_size: int = 20,
    conn=Depends(get_db),
    current_user=Depends(get_current_user),
):
    """当前用户的考试历史（已提交，按时间倒序）。"""
    uid = current_user["id"]
    offset = (page - 1) * page_size
    with conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) AS cnt FROM exams WHERE user_id = %s AND status = 'submitted'",
            (uid,),
        )
        total = cur.fetchone()["cnt"]
        cur.execute(
            """SELECT id, level, total, score, status,
                      DATE_FORMAT(created_at, '%%Y-%%m-%%d %%H:%%i') AS created_at,
                      DATE_FORMAT(submitted_at, '%%Y-%%m-%%d %%H:%%i') AS submitted_at
               FROM exams WHERE user_id = %s AND status = 'submitted'
               ORDER BY submitted_at DESC
               LIMIT %s OFFSET %s""",
            (uid, page_size, offset),
        )
        rows = cur.fetchall()
    items = [
        ExamSummary(
            id=r["id"],
            level=r["level"] or "",
            total=r["total"],
            score=r["score"],
            status=r["status"],
            created_at=r["created_at"] or "",
            submitted_at=r["submitted_at"],
        )
        for r in rows
    ]
    return ExamHistoryResponse(items=items, total=total)


@router.post("/generate", response_model=ExamOut, status_code=status.HTTP_201_CREATED)
def generate_exam(payload: ExamGenerateRequest, conn=Depends(get_db), current_user=Depends(get_current_user)):
    # 组卷筛选：复用题库的 WHERE 拼装思路
    where, params = [], []
    if payload.level:
        where.append("level = %s")
        params.append(payload.level)
    if payload.categories:
        placeholders = ", ".join(["%s"] * len(payload.categories))
        where.append(f"category IN ({placeholders})")
        params.extend(payload.categories)
    if payload.difficulty_range:
        lo, hi = payload.difficulty_range
        where.append("difficulty BETWEEN %s AND %s")
        params.extend([lo, hi])
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""

    try:
        with conn.cursor() as cursor:
            # 随机选题组；若库存不足则取实际可选数量
            cursor.execute(
                f"SELECT id FROM question_groups {where_sql} ORDER BY RAND() LIMIT %s",
                params + [payload.total_questions],
            )
            group_ids = [r["id"] for r in cursor.fetchall()]
            if not group_ids:
                raise HTTPException(status_code=422, detail="没有符合条件的题目，无法组卷")

            cursor.execute(
                "INSERT INTO exams (user_id, level, total, time_limit, status) VALUES (%s, %s, %s, %s, 'created')",
                (current_user["id"], payload.level or "", len(group_ids), payload.time_limit_minutes),
            )
            exam_id = cursor.lastrowid

            for seq, gid in enumerate(group_ids, start=1):
                cursor.execute(
                    "INSERT INTO exam_items (exam_id, seq, group_id) VALUES (%s, %s, %s)",
                    (exam_id, seq, gid),
                )
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    return _build_exam(conn, exam_id)


def _build_exam(conn, exam_id: int) -> ExamOut:
    """组装试卷（不含答案），供 generate 与 get 复用。"""
    with conn.cursor() as cursor:
        cursor.execute("SELECT id, level, total, time_limit, status FROM exams WHERE id = %s", (exam_id,))
        exam = cursor.fetchone()
        if exam is None:
            raise HTTPException(status_code=404, detail=f"试卷 {exam_id} 不存在")

        cursor.execute(
            "SELECT seq, group_id FROM exam_items WHERE exam_id = %s ORDER BY seq",
            (exam_id,),
        )
        items_raw = cursor.fetchall()

        items = []
        for it in items_raw:
            cursor.execute(
                "SELECT type, level FROM question_groups WHERE id = %s",
                (it["group_id"],),
            )
            g = cursor.fetchone()
            q = _first_question(cursor, it["group_id"])
            options = _group_options(cursor, q["id"]) if q else []
            items.append(
                ExamItemOut(
                    seq=it["seq"],
                    group_id=it["group_id"],
                    type=g["type"] if g else "",
                    level=(g["level"] or "") if g else "",
                    content=q["content"] if q else None,
                    marked=(q["marked"] or "") if q else "",
                    options=options,
                )
            )

    return ExamOut(
        id=exam["id"],
        level=exam["level"] or "",
        total=exam["total"],
        time_limit=exam["time_limit"] or 0,
        status=exam["status"],
        items=items,
    )


@router.get("/{exam_id}", response_model=ExamOut)
def get_exam(exam_id: int, conn=Depends(get_db), current_user=Depends(get_current_user)):
    with conn.cursor() as cur:
        cur.execute("SELECT user_id FROM exams WHERE id = %s", (exam_id,))
        row = cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"试卷 {exam_id} 不存在")
    if row["user_id"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="无权访问该试卷")
    return _build_exam(conn, exam_id)


@router.post("/{exam_id}/submit", response_model=ExamResultOut)
def submit_exam(exam_id: int, payload: SubmitRequest, conn=Depends(get_db), current_user=Depends(get_current_user)):
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id, status, user_id FROM exams WHERE id = %s", (exam_id,))
            exam = cursor.fetchone()
            if exam is None:
                raise HTTPException(status_code=404, detail=f"试卷 {exam_id} 不存在")
            if exam["user_id"] != current_user["id"]:
                raise HTTPException(status_code=403, detail="无权访问该试卷")
            if exam["status"] == "submitted":
                raise HTTPException(status_code=409, detail="试卷已提交，不能重复提交")

            # 建立 seq -> group_id 映射
            cursor.execute(
                "SELECT seq, group_id FROM exam_items WHERE exam_id = %s",
                (exam_id,),
            )
            seq_to_group = {r["seq"]: r["group_id"] for r in cursor.fetchall()}

            answer_map = {a.seq: a.answer for a in payload.answers}
            unknown = [s for s in answer_map if s not in seq_to_group]
            if unknown:
                raise HTTPException(status_code=422, detail=f"作答包含试卷中不存在的题号：{unknown}")

            score = 0
            for seq, gid in seq_to_group.items():
                user_ans = answer_map.get(seq)  # 未作答为 None
                q = _first_question(cursor, gid)
                correct = q["answer"] if q else ""
                is_correct = 1 if (user_ans is not None and user_ans == correct) else 0
                score += is_correct
                cursor.execute(
                    "UPDATE exam_items SET user_answer = %s, is_correct = %s WHERE exam_id = %s AND seq = %s",
                    (user_ans, is_correct, exam_id, seq),
                )

            cursor.execute(
                "UPDATE exams SET status = 'submitted', score = %s, submitted_at = NOW() WHERE id = %s",
                (score, exam_id),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    return _build_result(conn, exam_id)


def _build_result(conn, exam_id: int) -> ExamResultOut:
    """组装结果（含正确答案与解析），供 submit 与 result 复用。"""
    with conn.cursor() as cursor:
        cursor.execute("SELECT id, level, total, score, status FROM exams WHERE id = %s", (exam_id,))
        exam = cursor.fetchone()
        if exam is None:
            raise HTTPException(status_code=404, detail=f"试卷 {exam_id} 不存在")

        cursor.execute(
            "SELECT seq, group_id, user_answer, is_correct FROM exam_items WHERE exam_id = %s ORDER BY seq",
            (exam_id,),
        )
        rows = cursor.fetchall()

        items = []
        for r in rows:
            q = _first_question(cursor, r["group_id"])
            options = _group_options(cursor, q["id"]) if q else []
            items.append(
                ResultItemOut(
                    seq=r["seq"],
                    group_id=r["group_id"],
                    content=q["content"] if q else None,
                    marked=(q["marked"] or "") if q else "",
                    options=options,
                    user_answer=r["user_answer"],
                    correct_answer=q["answer"] if q else "",
                    is_correct=bool(r["is_correct"]),
                    analysis=q["analysis"] if q else None,
                )
            )

    return ExamResultOut(
        id=exam["id"],
        level=exam["level"] or "",
        total=exam["total"],
        score=exam["score"] or 0,
        status=exam["status"],
        items=items,
    )


@router.get("/{exam_id}/result", response_model=ExamResultOut)
def get_result(exam_id: int, conn=Depends(get_db), current_user=Depends(get_current_user)):
    with conn.cursor() as cur:
        cur.execute("SELECT user_id, status FROM exams WHERE id = %s", (exam_id,))
        exam = cur.fetchone()
    if exam is None:
        raise HTTPException(status_code=404, detail=f"试卷 {exam_id} 不存在")
    if exam["user_id"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="无权访问该试卷")
    if exam["status"] != "submitted":
        raise HTTPException(status_code=409, detail="试卷尚未提交，无结果可查")
    return _build_result(conn, exam_id)


@router.get("/{exam_id}/export")
def export_exam(
    exam_id: int,
    format: str = "markdown",
    with_answers: bool = False,
    conn=Depends(get_db),
    current_user=Depends(get_current_user),
):
    """导出试卷为可下载文件。当前支持 format=markdown。

    with_answers=False 仅题目卷；True 追加「答案与解析」一节。
    需为试卷所有者。前端用带 JWT 的请求拉取，作为附件下载。
    """
    if format != "markdown":
        raise HTTPException(status_code=400, detail=f"暂不支持的导出格式：{format}")

    with conn.cursor() as cur:
        cur.execute("SELECT user_id FROM exams WHERE id = %s", (exam_id,))
        exam = cur.fetchone()
        if exam is None:
            raise HTTPException(status_code=404, detail=f"试卷 {exam_id} 不存在")
        if exam["user_id"] != current_user["id"]:
            raise HTTPException(status_code=403, detail="无权访问该试卷")

        rendered = render_exam_markdown(cur, exam_id, with_answers=with_answers)

    if rendered is None:
        raise HTTPException(status_code=404, detail=f"试卷 {exam_id} 不存在")

    filename, content = rendered
    # RFC 5987 文件名编码，兼容中文
    disposition = f"attachment; filename*=UTF-8''{quote(filename)}"
    return Response(
        content=content,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": disposition},
    )

