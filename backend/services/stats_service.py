"""学习统计服务：薄弱知识点聚合（供 stats 路由与智能组卷复用）。"""
import json


def _parse_kp(raw) -> list:
    if raw is None or raw == "":
        return []
    if isinstance(raw, list):
        return raw
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []


def compute_weak_points(cur, user_id: int) -> list[dict]:
    """聚合用户已提交考试的错题知识点，返回按错题数降序的完整排名。

    每项：{point, wrong_count, total_count, error_rate}。无历史时返回 []。
    """
    cur.execute(
        """SELECT qg.knowledge_points, ei.is_correct
           FROM exam_items ei
           JOIN exams e ON ei.exam_id = e.id
           JOIN question_groups qg ON ei.group_id = qg.id
           WHERE e.user_id = %s AND e.status = 'submitted'""",
        (user_id,),
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
        result.append({
            "point": kp,
            "wrong_count": wrong,
            "total_count": total,
            "error_rate": round(wrong / total * 100, 1) if total else 0,
        })
    return result
