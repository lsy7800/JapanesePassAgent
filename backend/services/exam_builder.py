"""组卷核心服务：抽题 + 落库。

被两处复用：
- 手动组卷 `routers/exams.py::generate_exam`（题型 IN 单池随机）→ 调 persist_exam
- 智能组卷 `routers/exams.py::smart_generate` → 调 build_exam（按题型配额抽题）
Agent 工具 `tools.py::generate_exam` 暂保持独立实现，避免影响聊天流。

函数统一接收 pymysql DictCursor，事务由调用方提交。
"""
from backend.config.categories import category_name

MAX_PER_PLAN = 50


def persist_exam(cur, *, level: str | None, group_ids: list[int], time_limit: int, user_id: int | None) -> int:
    """把一批题组落库为一张试卷，返回 exam_id。group_ids 顺序即题目呈现顺序。

    判分细化到子题：每个题组按 questions.seq 展开成若干可评分子题——
    单选题一子题一行，完形/阅读多子题多行。exam_items.seq 为全局可评分题号（1..total），
    sub_seq 对应 questions.seq；exams.total 为子题总数。
    """
    # 展开各题组的子题，得到 (全局seq, group_id, sub_seq) 行
    rows: list[tuple[int, int, int]] = []
    gseq = 0
    for gid in group_ids:
        cur.execute("SELECT seq FROM questions WHERE group_id = %s ORDER BY seq", (gid,))
        subs = [r["seq"] for r in cur.fetchall()] or [1]
        for sub in subs:
            gseq += 1
            rows.append((gseq, gid, sub))
    total = gseq

    cur.execute(
        "INSERT INTO exams (user_id, level, total, time_limit, status) VALUES (%s, %s, %s, %s, 'created')",
        (user_id, level or "", total, time_limit or 0),
    )
    exam_id = cur.lastrowid
    for global_seq, gid, sub in rows:
        cur.execute(
            "INSERT INTO exam_items (exam_id, seq, group_id, sub_seq) VALUES (%s, %s, %s, %s)",
            (exam_id, global_seq, gid, sub),
        )
    return exam_id


def _select_group_ids(
    cur, *, level: str | None, category: str | None,
    difficulty_min: int | None, difficulty_max: int | None, count: int,
) -> list[int]:
    """从题库单池随机抽 count 个题组 id（库存不足则返回实际数量）。"""
    where, params = [], []
    if level:
        where.append("level = %s")
        params.append(level)
    if category:
        where.append("category = %s")
        params.append(category)
    if difficulty_min is not None:
        where.append("difficulty >= %s")
        params.append(difficulty_min)
    if difficulty_max is not None:
        where.append("difficulty <= %s")
        params.append(difficulty_max)
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    cur.execute(
        f"SELECT id FROM question_groups {where_sql} ORDER BY RAND() LIMIT %s",
        params + [count],
    )
    return [r["id"] for r in cur.fetchall()]


def build_exam(
    cur, *, level: str | None,
    plans: list[tuple[str | None, int]],
    difficulty_min: int | None = None,
    difficulty_max: int | None = None,
    time_limit: int = 0,
    user_id: int | None = None,
) -> dict:
    """按题型配额抽题并落库。

    plans: [(category|None, count), ...]，按顺序逐段抽题，题型间保持顺序、段内随机。
    返回 {exam_id, total, shortfalls}；无题可抽时 exam_id 为 None。
    """
    ordered_ids: list[int] = []
    shortfalls: list[str] = []
    for cat, cnt in plans:
        cnt = max(0, min(int(cnt), MAX_PER_PLAN))
        if not cnt:
            continue
        got = _select_group_ids(
            cur, level=level, category=cat,
            difficulty_min=difficulty_min, difficulty_max=difficulty_max, count=cnt,
        )
        ordered_ids.extend(got)
        if len(got) < cnt:
            label = category_name(cat) if cat else "全部题型"
            shortfalls.append(f"{label}：需 {cnt} 题，实际 {len(got)} 题")

    if not ordered_ids:
        return {"exam_id": None, "total": 0, "shortfalls": shortfalls}

    exam_id = persist_exam(
        cur, level=level, group_ids=ordered_ids, time_limit=time_limit, user_id=user_id,
    )
    return {"exam_id": exam_id, "total": len(ordered_ids), "shortfalls": shortfalls}
