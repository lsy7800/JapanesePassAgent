"""管理后台接口（全部要求 admin 角色）。

GET   /api/v1/admin/stats/overview      平台概览统计
GET   /api/v1/admin/stats/weak-points   跨全体用户的薄弱知识点排名
GET   /api/v1/admin/users               用户列表（分页 + 邮箱搜索 + 角色筛选）
PATCH /api/v1/admin/users/{user_id}     修改用户角色 / 启用状态
"""
import json

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.api.deps import get_db, require_admin
from backend.schemas.admin import (
    LabelCount,
    OverviewResponse,
    UserAdminOut,
    UserListResponse,
    UserUpdateRequest,
)
from backend.schemas.stats import WeakPoint, WeakPointsResponse

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


def _parse_kp(raw) -> list:
    if raw is None or raw == "":
        return []
    if isinstance(raw, list):
        return raw
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []


@router.get("/stats/overview", response_model=OverviewResponse)
def overview(conn=Depends(get_db), _=Depends(require_admin)):
    """题库 / 用户 / 考试 概览 + 级别、题型分布。"""
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS c FROM question_groups")
        total_questions = cur.fetchone()["c"]

        cur.execute("SELECT COUNT(*) AS c FROM users")
        total_users = cur.fetchone()["c"]

        cur.execute("SELECT COUNT(*) AS c FROM exams WHERE status = 'submitted'")
        total_exams = cur.fetchone()["c"]

        # 全平台平均正确率：sum(score)/sum(total)
        cur.execute(
            """SELECT COALESCE(SUM(score), 0) AS s, COALESCE(SUM(total), 0) AS t
               FROM exams WHERE status = 'submitted' AND score IS NOT NULL"""
        )
        row = cur.fetchone()
        avg_accuracy = round(row["s"] / row["t"] * 100, 1) if row["t"] else 0.0

        cur.execute(
            """SELECT COALESCE(level, '未分级') AS label, COUNT(*) AS count
               FROM question_groups GROUP BY level ORDER BY level"""
        )
        by_level = [LabelCount(label=r["label"], count=r["count"]) for r in cur.fetchall()]

        cur.execute(
            "SELECT type AS label, COUNT(*) AS count FROM question_groups GROUP BY type ORDER BY type"
        )
        by_type = [LabelCount(label=r["label"], count=r["count"]) for r in cur.fetchall()]

    return OverviewResponse(
        total_questions=total_questions,
        total_users=total_users,
        total_exams=total_exams,
        avg_accuracy=avg_accuracy,
        by_level=by_level,
        by_type=by_type,
    )


@router.get("/stats/weak-points", response_model=WeakPointsResponse)
def platform_weak_points(
    limit: int = Query(default=10, ge=1, le=50),
    conn=Depends(get_db),
    _=Depends(require_admin),
):
    """跨全体用户聚合错题 knowledge_points，反映平台整体薄弱点。"""
    with conn.cursor() as cur:
        cur.execute(
            """SELECT qg.knowledge_points, ei.is_correct
               FROM exam_items ei
               JOIN exams e ON ei.exam_id = e.id
               JOIN question_groups qg ON ei.group_id = qg.id
               WHERE e.status = 'submitted'"""
        )
        rows = cur.fetchall()

    kp_wrong: dict[str, int] = {}
    kp_total: dict[str, int] = {}
    for r in rows:
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


@router.get("/users", response_model=UserListResponse)
def list_users(
    q: str | None = Query(default=None, description="邮箱模糊搜索"),
    role: str | None = Query(default=None, pattern="^(student|admin)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    conn=Depends(get_db),
    _=Depends(require_admin),
):
    where = []
    params = []
    if q:
        where.append("u.email LIKE %s")
        params.append(f"%{q}%")
    if role:
        where.append("u.role = %s")
        params.append(role)
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""

    with conn.cursor() as cur:
        cur.execute(f"SELECT COUNT(*) AS total FROM users u {where_sql}", params)
        total = cur.fetchone()["total"]

        offset = (page - 1) * page_size
        cur.execute(
            f"""SELECT u.id, u.email, u.role, u.is_active,
                       DATE_FORMAT(u.created_at, '%%Y-%%m-%%d %%H:%%i') AS created_at,
                       (SELECT COUNT(*) FROM exams e
                        WHERE e.user_id = u.id AND e.status = 'submitted') AS exam_count
                FROM users u {where_sql}
                ORDER BY u.id
                LIMIT %s OFFSET %s""",
            params + [page_size, offset],
        )
        rows = cur.fetchall()

    items = [
        UserAdminOut(
            id=r["id"],
            email=r["email"],
            role=r["role"],
            is_active=bool(r["is_active"]),
            created_at=r["created_at"] or "",
            exam_count=r["exam_count"],
        )
        for r in rows
    ]
    return UserListResponse(items=items, page=page, page_size=page_size, total=total)


@router.patch("/users/{user_id}", response_model=UserAdminOut)
def update_user(
    user_id: int,
    payload: UserUpdateRequest,
    conn=Depends(get_db),
    admin=Depends(require_admin),
):
    """修改用户角色或启用状态。禁止管理员停用/降级自己，避免自锁。"""
    if user_id == admin["id"]:
        if payload.is_active is False:
            raise HTTPException(status_code=400, detail="不能停用自己的账号")
        if payload.role == "student":
            raise HTTPException(status_code=400, detail="不能降级自己的账号")

    with conn.cursor() as cur:
        cur.execute("SELECT id FROM users WHERE id = %s", (user_id,))
        if cur.fetchone() is None:
            raise HTTPException(status_code=404, detail="用户不存在")

        sets = []
        params = []
        if payload.role is not None:
            sets.append("role = %s")
            params.append(payload.role)
        if payload.is_active is not None:
            sets.append("is_active = %s")
            params.append(payload.is_active)
        if sets:
            params.append(user_id)
            cur.execute(f"UPDATE users SET {', '.join(sets)} WHERE id = %s", params)

        cur.execute(
            """SELECT u.id, u.email, u.role, u.is_active,
                      DATE_FORMAT(u.created_at, '%%Y-%%m-%%d %%H:%%i') AS created_at,
                      (SELECT COUNT(*) FROM exams e
                       WHERE e.user_id = u.id AND e.status = 'submitted') AS exam_count
               FROM users u WHERE u.id = %s""",
            (user_id,),
        )
        r = cur.fetchone()
    conn.commit()

    return UserAdminOut(
        id=r["id"],
        email=r["email"],
        role=r["role"],
        is_active=bool(r["is_active"]),
        created_at=r["created_at"] or "",
        exam_count=r["exam_count"],
    )
