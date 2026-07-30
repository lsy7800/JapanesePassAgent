"""考试/组卷接口。

对应 README「API 设计 - 考试与做题」：
- POST /api/v1/exams/generate       智能组卷（随机选题，落库，返回不含答案的试卷）
- GET  /api/v1/exams/{exam_id}       获取试卷内容（不含答案）
- POST /api/v1/exams/{exam_id}/submit 提交答案并判分
- GET  /api/v1/exams/{exam_id}/result 获取结果（含正确答案与解析）

判分细化到子题级：单选题一题组一子题；完形/阅读一题组多子题，逐子题比对答案。
不调用 LLM，纯比对，结果确定。
"""
import json
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import StreamingResponse

from backend.api.deps import auth_by_query_token, get_db, get_current_user
from backend.api.exam_export import VALID_MODES, render_exam_markdown
from backend.services.exam_builder import persist_exam
from backend.services.smart_exam import NoQuestionsError, run_smart_exam, stream_smart_exam
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
    """取题组元信息（题型/级别/文章/听力音频）。"""
    cursor.execute(
        "SELECT type, level, article, audio_url FROM question_groups WHERE id = %s",
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


@router.delete("")
def clear_exams(
    scope: str = "drafts",
    conn=Depends(get_db),
    current_user=Depends(get_current_user),
):
    """清空当前用户的考试数据。

    scope：
    - drafts（默认）只删未提交且零作答的草稿——「组了没做」的卷，删了不损失任何记录
    - all              删全部考试数据，含已提交的历史分数

    **只删自己的**：user_id 取自 JWT，不接受调用方指定，避免越权清空他人数据。
    exam_items 由外键 ON DELETE CASCADE 一并清理。

    注意 scope=all 的连带影响：薄弱点与学习统计都是从 exam_items 实时聚合的
    （无独立统计表），清空后会一并归零，AI 智能组卷将退回「按级别均衡出题」。
    """
    if scope not in ("drafts", "all"):
        raise HTTPException(
            status_code=400, detail=f"未知清空范围：{scope}（可选 drafts/all）"
        )
    uid = current_user["id"]

    with conn.cursor() as cur:
        if scope == "all":
            where, params = "user_id = %s", (uid,)
        else:
            # 草稿定义：未提交，且没有任何一条作答记录——只要动过就不算草稿，
            # 避免把「做了一半还想接着做」的卷当成垃圾清掉
            where = """user_id = %s AND status = 'created'
                       AND id NOT IN (
                           SELECT DISTINCT exam_id FROM exam_items
                           WHERE user_answer IS NOT NULL AND user_answer <> ''
                       )"""
            params = (uid,)

        # 先统计再删，好让前端能明确告知「清掉了多少」
        cur.execute(f"SELECT COUNT(*) AS n FROM exams WHERE {where}", params)
        exams_n = cur.fetchone()["n"]
        cur.execute(
            f"""SELECT COUNT(*) AS n FROM exam_items
                WHERE exam_id IN (SELECT id FROM exams WHERE {where})""",
            params,
        )
        items_n = cur.fetchone()["n"]

        cur.execute(f"DELETE FROM exams WHERE {where}", params)
        conn.commit()

    return {"ok": True, "scope": scope, "deleted_exams": exams_n, "deleted_items": items_n}


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
    """AI 智能组卷（一次性返回）：结合用户薄弱点，让 LLM 规划抽题方案并落库为可作答试卷。

    流程：薄弱点聚合 → LLM 规划（内部已兜底，绝不因 LLM 异常而挂）→ 确定性建卷 → 返回不含答案的试卷 + 组卷说明。
    LLM 规划通常十几秒，期间前端只能干等；需要阶段化进度时改用 /smart-generate/stream。
    """
    try:
        result = run_smart_exam(
            payload.requirement, payload.level, payload.time_limit_minutes,
            current_user["id"], conn=conn,
        )
    except NoQuestionsError as e:
        raise HTTPException(status_code=422, detail=str(e))

    exam = _build_exam(conn, result["exam_id"])
    return SmartExamOut(
        **exam.model_dump(),
        rationale=result["plan"]["rationale"],
        shortfalls=result["shortfalls"],
    )


@router.get("/smart-generate/stream")
async def smart_generate_stream(
    requirement: str = Query(..., min_length=1, max_length=500, description="自然语言组卷需求"),
    level: str | None = Query(default=None, description="目标级别 N1~N5，不传由 AI 决定"),
    time_limit_minutes: int = Query(default=0, ge=0, le=180, description="限时（分钟），0 不限"),
    token: str = Query(default="", description="JWT access_token（EventSource 不支持 Header，走 query）"),
    conn=Depends(get_db),
):
    """AI 智能组卷的 SSE 版本：逐阶段推送进度，最后给出 exam_id。

    组卷要串行跑「薄弱点聚合 → LLM 规划 → 抽题落库」，其中 LLM 一步就要十几秒。
    这里把每一步的开始/结果推给前端，方案确定时先送出 rationale，用户能看到 AI
    的组卷思路而不是干等转圈。前端收到 done 后再用 GET /exams/{id} 取试卷正文。
    """
    user_id = auth_by_query_token(token, conn)

    async def gen():
        async for event in stream_smart_exam(requirement, level, time_limit_minutes, user_id):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
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
                    audio_url=g.get("audio_url") if g else None,
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
                    audio_url=g.get("audio_url") if g else None,
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
    mode: str | None = None,
    conn=Depends(get_db),
    current_user=Depends(get_current_user),
):
    """导出试卷为可下载文件。当前支持 format=markdown。

    mode（推荐）：
    - questions      仅题目卷
    - with_answers   题目卷 + 「答案与解析」一节
    - answers_only   只有答案与解析，不含题目（对答案、批改用）

    with_answers 为兼容旧前端保留：未传 mode 时 True→with_answers、False→questions。
    需为试卷所有者。前端用带 JWT 的请求拉取，作为附件下载。
    """
    if format != "markdown":
        raise HTTPException(status_code=400, detail=f"暂不支持的导出格式：{format}")
    if mode is not None and mode not in VALID_MODES:
        raise HTTPException(
            status_code=400,
            detail=f"未知导出模式：{mode}（可选 {'/'.join(VALID_MODES)}）",
        )

    with conn.cursor() as cur:
        cur.execute("SELECT user_id FROM exams WHERE id = %s", (exam_id,))
        exam = cur.fetchone()
        if exam is None:
            raise HTTPException(status_code=404, detail=f"试卷 {exam_id} 不存在")
        if exam["user_id"] != current_user["id"]:
            raise HTTPException(status_code=403, detail="无权访问该试卷")

        rendered = render_exam_markdown(
            cur, exam_id, with_answers=with_answers, mode=mode
        )

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

