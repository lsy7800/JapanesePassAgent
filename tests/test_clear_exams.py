"""清空个人考试数据接口测试。

关键约束：只能删自己的（user_id 取自 JWT，不接受传参），否则是越权漏洞。
drafts 范围只删「组了没做」的卷，不能碰已提交或做了一半的。
"""
import pytest

from backend.services.exam_builder import build_exam


@pytest.fixture
def seed(db):
    """播种可抽题的题库，返回题型 code。"""
    with db.cursor() as cur:
        for i in range(6):
            cur.execute(
                """INSERT INTO question_groups
                   (type, category, level, exam_date, difficulty, knowledge_points, source, source_ref)
                   VALUES ('single_choice','kanji_reading','N1','2022-07',3,'[]','tst',%s)""",
                (f"tst#{i}",),
            )
            gid = cur.lastrowid
            cur.execute(
                "INSERT INTO questions (group_id, seq, content, answer) VALUES (%s,1,%s,'a')",
                (gid, f"题干{i}"),
            )
            qid = cur.lastrowid
            for lb in ("a", "b", "c", "d"):
                cur.execute(
                    "INSERT INTO options (question_id,label,content) VALUES (%s,%s,%s)",
                    (qid, lb, f"选项{lb}"),
                )
    db.commit()
    return "kanji_reading"


def _make_exam(db, uid, cat, *, submitted=False, answered=False):
    with db.cursor() as cur:
        b = build_exam(cur, level="N1", plans=[(cat, 2)], user_id=uid)
        eid = b["exam_id"]
        if answered:
            cur.execute(
                "UPDATE exam_items SET user_answer='a', is_correct=1 WHERE exam_id=%s", (eid,)
            )
        if submitted:
            cur.execute(
                "UPDATE exams SET status='submitted', score=1, submitted_at=NOW() WHERE id=%s",
                (eid,),
            )
    db.commit()
    return eid


def _ids(db, uid):
    with db.cursor() as cur:
        cur.execute("SELECT id FROM exams WHERE user_id=%s ORDER BY id", (uid,))
        return [r["id"] for r in cur.fetchall()]


def test_drafts_scope_keeps_submitted_and_answered(client, db, make_user, seed):
    """drafts 只删「组了没做」的：已提交、做了一半的都要保留。"""
    u = make_user()
    draft = _make_exam(db, u["id"], seed)
    partial = _make_exam(db, u["id"], seed, answered=True)
    done = _make_exam(db, u["id"], seed, submitted=True, answered=True)

    r = client.delete("/api/v1/exams", params={"scope": "drafts"}, headers=u["headers"])
    assert r.status_code == 200
    assert r.json()["deleted_exams"] == 1

    db.rollback()
    remaining = _ids(db, u["id"])
    assert draft not in remaining, "草稿未删"
    assert partial in remaining, "做了一半的被误删"
    assert done in remaining, "已提交的被误删"


def test_all_scope_clears_everything(client, db, make_user, seed):
    u = make_user()
    _make_exam(db, u["id"], seed)
    _make_exam(db, u["id"], seed, submitted=True, answered=True)

    r = client.delete("/api/v1/exams", params={"scope": "all"}, headers=u["headers"])
    assert r.status_code == 200
    body = r.json()
    assert body["deleted_exams"] == 2
    assert body["deleted_items"] == 4  # 每卷 2 题

    db.rollback()
    assert _ids(db, u["id"]) == []


def test_exam_items_cascade_deleted(client, db, make_user, seed):
    """删 exams 应级联清掉 exam_items，不留孤儿。"""
    u = make_user()
    eid = _make_exam(db, u["id"], seed)
    client.delete("/api/v1/exams", params={"scope": "all"}, headers=u["headers"])

    db.rollback()
    with db.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS n FROM exam_items WHERE exam_id=%s", (eid,))
        assert cur.fetchone()["n"] == 0


def test_only_deletes_own_data(client, db, make_user, seed):
    """核心安全约束：不能删到别人的数据。"""
    mine = make_user(email="mine@test.com")
    other = make_user(email="other@test.com")
    my_exam = _make_exam(db, mine["id"], seed)
    other_exam = _make_exam(db, other["id"], seed)

    client.delete("/api/v1/exams", params={"scope": "all"}, headers=mine["headers"])

    db.rollback()
    assert my_exam not in _ids(db, mine["id"])
    assert other_exam in _ids(db, other["id"]), "删到了别人的试卷！"


def test_defaults_to_drafts(client, db, make_user, seed):
    """不传 scope 时按 drafts 处理——默认走破坏性更小的那个。"""
    u = make_user()
    done = _make_exam(db, u["id"], seed, submitted=True, answered=True)
    client.delete("/api/v1/exams", headers=u["headers"])
    db.rollback()
    assert done in _ids(db, u["id"]), "默认竟然删了已提交的卷"


def test_rejects_unknown_scope(client, make_user):
    u = make_user()
    r = client.delete("/api/v1/exams", params={"scope": "bogus"}, headers=u["headers"])
    assert r.status_code == 400
    assert "未知清空范围" in r.json()["detail"]


def test_requires_auth(client):
    assert client.delete("/api/v1/exams").status_code == 401


def test_empty_is_not_an_error(client, db, make_user):
    """没有数据时清空应正常返回 0，而不是报错。"""
    u = make_user()
    r = client.delete("/api/v1/exams", params={"scope": "all"}, headers=u["headers"])
    assert r.status_code == 200
    assert r.json()["deleted_exams"] == 0
