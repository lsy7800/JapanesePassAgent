"""学习分析接口。

GET  /api/v1/stats/weak-points      薄弱知识点排名（跨多次考试聚合）
GET  /api/v1/stats/history          考试趋势（每次考试的日期/得分/正确率）
POST /api/v1/review/wrong-questions 错题集（去重，可按知识点筛选）
"""
import json

from fastapi import APIRouter, Depends, Query

from backend.api.deps import get_db, get_current_user
from backend.schemas.stats import (
    WrongQuestionsRequest,
    WrongQuestionsResponse,
    WrongQuestionItem,
    WeakPoint,
    WeakPointsResponse,
    HistoryPoint,
    HistoryResponse,
)

router = APIRouter(tags=["stats"])


def _parse_kp(raw) -> list:
    if raw is None or raw == "":
        return []
    if isinstance(raw, list):
        return raw
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []


@router.get("/api/v1/stats/weak-points", response_model=WeakPointsResponse)
def weak_points(
    limit: int = Query(default=10, ge=1, le=50),
    conn=Depends(get_db),
    current_user=Depends(get_current_user),
):
    """跨多次考试聚合错题 knowledge_points，返回薄弱点排名。"""
    uid = current_user["id"]
    with conn.cursor() as cur:
        # 查该用户所有答错的题组
        cur.execute(
            """SELECT qg.knowledge_points
               FROM exam_items ei
               JOIN exams e ON ei.exam_id = e.id
               JOIN question_groups qg ON ei.group_id = qg.id
               WHERE e.user_id = %s AND ei.is_correct = 0 AND e.status = 'submitted'""",
            (uid,),
        )
        rows = cur.fetchall()

        # 统计总答题数（含正确），用于计算错误率
        cur.execute(
            """SELECT qg.knowledge_points, ei.is_correct
               FROM exam_items ei
               JOIN exams e ON ei.exam_id = e.id
               JOIN question_groups qg ON ei.group_id = qg.id
               WHERE e.user_id = %s AND e.status = 'submitted'""",
            (uid,),
        )
        all_rows = cur.fetchall()

    kp_wrong: dict[str, int] = {}
    kp_total: dict[str, int] = {}

    for r in all_rows:
        for kp in _parse_kp(r["knowledge_points"]):
            kp_total[kp] = kp_total.get(kp, 0) + 1
            if not r["is_correct"]:
                kp_wrong[kp] = kp_wrong.get(kp, 0) + 1

    result = []
    for kp, wrong in sorted(kp_wrong.items(), key=lambda x: -x[1]):
        total = kp_total.get(kp, wrong)
        result.append(WeakPoint(
            point=kp,
            wrong_count=wrong,
            total_count=total,
            error_rate=round(wrong / total * 100, 1) if total else 0,
        ))

    return WeakPointsResponse(items=result[:limit], total=len(result))


@router.get("/api/v1/stats/history", response_model=HistoryResponse)
def exam_history_trend(
    limit: int = Query(default=20, ge=1, le=100),
    conn=Depends(get_db),
    current_user=Depends(get_current_user),
):
    """近 N 次考试的趋势数据（日期/得分/正确率）。"""
    uid = current_user["id"]
    with conn.cursor() as cur:
        cur.execute(
            """SELECT id, level, total, score,
                      DATE_FORMAT(submitted_at, '%%m-%%d %%H:%%i') AS date
               FROM exams
               WHERE user_id = %s AND status = 'submitted' AND score IS NOT NULL
               ORDER BY submitted_at DESC
               LIMIT %s""",
            (uid, limit),
        )
        rows = cur.fetchall()

    points = [
        HistoryPoint(
            exam_id=r["id"],
            date=r["date"] or "",
            level=r["level"] or "综合",
            total=r["total"],
            score=r["score"] or 0,
            accuracy=round((r["score"] or 0) / r["total"] * 100, 1) if r["total"] else 0,
        )
        for r in reversed(rows)  # 时间正序展示
    ]
    return HistoryResponse(points=points)


@router.post("/api/v1/review/wrong-questions", response_model=WrongQuestionsResponse)
def wrong_questions(
    payload: WrongQuestionsRequest,
    conn=Depends(get_db),
    current_user=Depends(get_current_user),
):
    """错题集：查询用户答错的题目，去重，可按知识点筛选。"""
    uid = current_user["id"]
    with conn.cursor() as cur:
        # 取该用户所有错题的 group_id（去重）
        cur.execute(
            """SELECT DISTINCT ei.group_id
               FROM exam_items ei
               JOIN exams e ON ei.exam_id = e.id
               WHERE e.user_id = %s AND ei.is_correct = 0 AND e.status = 'submitted'""",
            (uid,),
        )
        group_ids = [r["group_id"] for r in cur.fetchall()]

    if not group_ids:
        return WrongQuestionsResponse(items=[], total=0)

    with conn.cursor() as cur:
        # 获取题组信息，按知识点筛选
        placeholders = ",".join(["%s"] * len(group_ids))
        cur.execute(
            f"SELECT id, level, type, difficulty, knowledge_points FROM question_groups WHERE id IN ({placeholders})",
            group_ids,
        )
        groups = {r["id"]: r for r in cur.fetchall()}

    # 知识点筛选
    if payload.knowledge_point:
        kp = payload.knowledge_point
        groups = {
            gid: g for gid, g in groups.items()
            if kp in _parse_kp(g["knowledge_points"])
        }

    if not groups:
        return WrongQuestionsResponse(items=[], total=0)

    # 分页
    page = payload.page or 1
    page_size = payload.page_size or 20
    total = len(groups)
    paged_ids = list(groups.keys())[(page - 1) * page_size: page * page_size]

    items = []
    with conn.cursor() as cur:
        for gid in paged_ids:
            g = groups[gid]
            cur.execute(
                "SELECT id, content, answer, analysis FROM questions WHERE group_id = %s ORDER BY seq LIMIT 1",
                (gid,),
            )
            q = cur.fetchone()
            if not q:
                continue
            cur.execute(
                "SELECT label, content FROM options WHERE question_id = %s ORDER BY label",
                (q["id"],),
            )
            options = {o["label"]: o["content"] for o in cur.fetchall()}
            items.append(WrongQuestionItem(
                group_id=gid,
                level=g["level"] or "",
                knowledge_points=_parse_kp(g["knowledge_points"]),
                content=q["content"] or "",
                options=options,
                correct_answer=q["answer"],
                analysis=q["analysis"] or "",
            ))

    return WrongQuestionsResponse(items=items, total=total)
