"""考试/组卷接口。

对应 README「API 设计 - 考试与做题」：
- POST /api/v1/exams/generate       智能组卷（随机选题，落库，返回不含答案的试卷）
- GET  /api/v1/exams/{exam_id}       获取试卷内容（不含答案）
- POST /api/v1/exams/{exam_id}/submit 提交答案并判分
- GET  /api/v1/exams/{exam_id}/result 获取结果（含正确答案与解析）

判分细化到子题级：单选题一题组一子题；完形/阅读一题组多子题，逐子题比对答案。
不调用 LLM，纯比对，结果确定。
"""
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Response, status

from backend.api.deps import get_db, get_current_user
from backend.api.exam_export import render_exam_markdown
from backend.config.categories import get_categories
from backend.services.exam_builder import build_exam, persist_exam
from backend.services.exam_planner import plan_exam
from backend.services.stats_service import compute_weak_points
from backend.schemas.exam import (
    ExamGenerateRequest,
    ExamHistoryResponse,
    ExamItemOut,
    ExamOptionOut,
    ExamOut,
    ExamResultOut,
    ExamSubQuestion,
    ExamSummary,
    ResultItemOut,
    ResultSubQuestion,
    SmartExamOut,
    SmartExamRequest,
    SubmitRequest,
)

router = APIRouter(prefix="/api/v1/exams", tags=["exams"])


def _group_options(cursor, question_id: int) -> list[ExamOptionOut]:
    cursor.execute(
        "SELECT label, content FROM options WHERE question_id = %s ORDER BY label",
        (question_id,),
    )
    return [ExamOptionOut(label=o["label"], content=o["content"]) for o in cursor.fetchall()]


def _group_meta(cursor, group_id: int):
    """取题组元信息（题型/级别/文章）。"""
    cursor.execute(
        "SELECT type, level, article FROM question_groups WHERE id = %s",
        (group_id,),
    )
    return cursor.fetchone()


def _sub_question(cursor, group_id: int, sub_seq: int):
    """取题组内指定子题（按 questions.seq 定位；含 answer/analysis/content）。"""
    cursor.execute(
        """SELECT id, content, marked, answer, analysis
           FROM questions WHERE group_id = %s AND seq = %s LIMIT 1""",
        (group_id, sub_seq),
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

            exam_id = persist_exam(
                cursor,
                level=payload.level,
                group_ids=group_ids,
                time_limit=payload.time_limit_minutes,
                user_id=current_user["id"],
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    return _build_exam(conn, exam_id)


@router.post("/smart-generate", response_model=SmartExamOut, status_code=status.HTTP_201_CREATED)
def smart_generate(
    payload: SmartExamRequest,
    conn=Depends(get_db),
    current_user=Depends(get_current_user),
):
    """AI 智能组卷：结合用户薄弱点，让 LLM 规划抽题方案并落库为可作答试卷。

    流程：薄弱点聚合 → LLM 规划（内部已兜底，绝不因 LLM 异常而挂）→ 确定性建卷 → 返回不含答案的试卷 + 组卷说明。
    """
    uid = current_user["id"]

    with conn.cursor() as cur:
        weak = compute_weak_points(cur, uid)

    available = [
        {"code": c["code"], "name": c["name"]}
        for c in get_categories(level=payload.level, examable_only=True)
    ]

    plan = plan_exam(payload.requirement, weak[:8], payload.level, available)

    quotas = plan.get("category_quotas")
    if quotas:
        plans = [(code, cnt) for code, cnt in quotas.items()]
    else:
        plans = [(None, plan["total_questions"])]

    try:
        with conn.cursor() as cur:
            result = build_exam(
                cur,
                level=plan["level"],
                plans=plans,
                difficulty_min=plan.get("difficulty_min"),
                difficulty_max=plan.get("difficulty_max"),
                time_limit=payload.time_limit_minutes,
                user_id=uid,
            )
            if not result["exam_id"]:
                raise HTTPException(status_code=422, detail="没有符合条件的题目，请调整需求后再试")
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    exam = _build_exam(conn, result["exam_id"])
    return SmartExamOut(
        **exam.model_dump(),
        rationale=plan["rationale"],
        shortfalls=result["shortfalls"],
    )


def _build_exam(conn, exam_id: int) -> ExamOut:
    """组装试卷（不含答案），供 generate 与 get 复用。

    exam_items 逐子题一行；按 group_id 分组成卡片（单选题一卡一子题，完形题一卡文章 + N 子题）。
    """
    with conn.cursor() as cursor:
        cursor.execute("SELECT id, level, total, time_limit, status FROM exams WHERE id = %s", (exam_id,))
        exam = cursor.fetchone()
        if exam is None:
            raise HTTPException(status_code=404, detail=f"试卷 {exam_id} 不存在")

        cursor.execute(
            "SELECT seq, group_id, sub_seq FROM exam_items WHERE exam_id = %s ORDER BY seq",
            (exam_id,),
        )
        rows = cursor.fetchall()

        items: list[ExamItemOut] = []
        for r in rows:
            # rows 按 seq 升序、同题组连续 → 题组变化时开一张新卡片
            if not items or items[-1].group_id != r["group_id"]:
                g = _group_meta(cursor, r["group_id"])
                items.append(ExamItemOut(
                    seq=len(items) + 1,
                    group_id=r["group_id"],
                    type=g["type"] if g else "",
                    level=(g["level"] or "") if g else "",
                    article=g["article"] if g else None,
                    questions=[],
                ))
            q = _sub_question(cursor, r["group_id"], r["sub_seq"])
            options = _group_options(cursor, q["id"]) if q else []
            items[-1].questions.append(ExamSubQuestion(
                no=r["seq"],
                sub_seq=r["sub_seq"],
                content=q["content"] if q else None,
                marked=(q["marked"] or "") if q else "",
                options=options,
            ))

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

            # 逐子题作答：seq 为全局可评分题号
            cursor.execute(
                "SELECT seq, group_id, sub_seq FROM exam_items WHERE exam_id = %s",
                (exam_id,),
            )
            item_rows = cursor.fetchall()
            valid_seqs = {r["seq"] for r in item_rows}

            answer_map = {a.seq: a.answer for a in payload.answers}
            unknown = [s for s in answer_map if s not in valid_seqs]
            if unknown:
                raise HTTPException(status_code=422, detail=f"作答包含试卷中不存在的题号：{unknown}")

            score = 0
            for r in item_rows:
                user_ans = answer_map.get(r["seq"])  # 未作答为 None
                q = _sub_question(cursor, r["group_id"], r["sub_seq"])
                correct = q["answer"] if q else ""
                is_correct = 1 if (user_ans is not None and user_ans == correct) else 0
                score += is_correct
                cursor.execute(
                    "UPDATE exam_items SET user_answer = %s, is_correct = %s WHERE exam_id = %s AND seq = %s",
                    (user_ans, is_correct, exam_id, r["seq"]),
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
    """组装结果（含正确答案与解析），供 submit 与 result 复用。按 group_id 分组成卡片。"""
    with conn.cursor() as cursor:
        cursor.execute("SELECT id, level, total, score, status FROM exams WHERE id = %s", (exam_id,))
        exam = cursor.fetchone()
        if exam is None:
            raise HTTPException(status_code=404, detail=f"试卷 {exam_id} 不存在")

        cursor.execute(
            "SELECT seq, group_id, sub_seq, user_answer, is_correct FROM exam_items WHERE exam_id = %s ORDER BY seq",
            (exam_id,),
        )
        rows = cursor.fetchall()

        items: list[ResultItemOut] = []
        for r in rows:
            if not items or items[-1].group_id != r["group_id"]:
                g = _group_meta(cursor, r["group_id"])
                items.append(ResultItemOut(
                    seq=len(items) + 1,
                    group_id=r["group_id"],
                    type=g["type"] if g else "",
                    article=g["article"] if g else None,
                    questions=[],
                ))
            q = _sub_question(cursor, r["group_id"], r["sub_seq"])
            options = _group_options(cursor, q["id"]) if q else []
            items[-1].questions.append(ResultSubQuestion(
                no=r["seq"],
                sub_seq=r["sub_seq"],
                content=q["content"] if q else None,
                marked=(q["marked"] or "") if q else "",
                options=options,
                user_answer=r["user_answer"],
                correct_answer=q["answer"] if q else "",
                is_correct=bool(r["is_correct"]),
                analysis=q["analysis"] if q else None,
            ))

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

