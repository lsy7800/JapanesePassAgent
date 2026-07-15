"""文章完形（cloze）在线考试端到端测试：嵌套结构 + 逐空判分。

覆盖 shitibiao 73 引入的多子题题型在考试流程中的支持：
一篇文章 → 一张卡片含 N 子题，作答/判分细化到子题级。
"""
import pytest


@pytest.fixture
def seed_cloze(db):
    """插入一个完形题组：文章 + 3 空，正确答案 a/b/c；每空 4 选项。"""
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO question_groups (type, category, article, level, source) "
            "VALUES ('cloze', 'text_grammar', %s, 'N1', 'test_cloze')",
            ("これはテスト。（1）、（2）、（3）。",),
        )
        gid = cur.lastrowid
        for seq, ans in enumerate(["a", "b", "c"], start=1):
            cur.execute(
                "INSERT INTO questions (group_id, seq, content, answer) VALUES (%s, %s, '', %s)",
                (gid, seq, ans),
            )
            qid = cur.lastrowid
            for lab in ["a", "b", "c", "d"]:
                cur.execute(
                    "INSERT INTO options (question_id, label, content) VALUES (%s, %s, %s)",
                    (qid, lab, f"选项{lab}"),
                )
    db.commit()
    return gid


def test_cloze_generate_nested(client, make_user, seed_cloze):
    """完形题组卷：一张卡片含文章 + 3 子题，全局题号 1..3，不含答案。"""
    u = make_user()
    r = client.post(
        "/api/v1/exams/generate",
        json={"level": "N1", "categories": ["text_grammar"], "total_questions": 1},
        headers=u["headers"],
    )
    assert r.status_code == 201
    body = r.json()
    assert body["total"] == 3            # 子题总数
    assert len(body["items"]) == 1       # 一张卡片
    card = body["items"][0]
    assert card["type"] == "cloze"
    assert card["article"]
    assert [q["no"] for q in card["questions"]] == [1, 2, 3]
    assert [q["sub_seq"] for q in card["questions"]] == [1, 2, 3]
    # 作答阶段不泄漏答案
    sub = card["questions"][0]
    assert "answer" not in sub and "correct_answer" not in sub
    assert len(sub["options"]) == 4


def test_cloze_submit_scores_per_blank(client, make_user, seed_cloze):
    """逐空判分：第1、2空对，第3空错 → 得分 2/3，结果携带每空对错与正解。"""
    u = make_user()
    r = client.post(
        "/api/v1/exams/generate",
        json={"level": "N1", "categories": ["text_grammar"], "total_questions": 1},
        headers=u["headers"],
    )
    exam_id = r.json()["id"]

    # 正解 a/b/c；第3空故意选 a（应为 c）
    answers = [{"seq": 1, "answer": "a"}, {"seq": 2, "answer": "b"}, {"seq": 3, "answer": "a"}]
    sr = client.post(f"/api/v1/exams/{exam_id}/submit", json={"answers": answers}, headers=u["headers"])
    assert sr.status_code == 200
    res = sr.json()
    assert res["total"] == 3
    assert res["score"] == 2

    card = res["items"][0]
    assert card["type"] == "cloze"
    assert card["article"]
    q1, q2, q3 = card["questions"]
    assert q1["is_correct"] is True and q1["correct_answer"] == "a"
    assert q2["is_correct"] is True
    assert q3["is_correct"] is False
    assert q3["correct_answer"] == "c" and q3["user_answer"] == "a"


def test_cloze_and_single_choice_global_numbering(client, make_user, seed_cloze, db):
    """完形（3空）+ 单选各 1 组同卷：全局题号连续、total 为子题总数。"""
    # 追加一个单选题组
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO question_groups (type, category, level, source) "
            "VALUES ('single_choice', 'kanji_reading', 'N1', 'test_single')"
        )
        gid = cur.lastrowid
        cur.execute(
            "INSERT INTO questions (group_id, seq, content, answer) VALUES (%s, 1, '单题', 'd')",
            (gid,),
        )
        qid = cur.lastrowid
        for lab in ["a", "b", "c", "d"]:
            cur.execute(
                "INSERT INTO options (question_id, label, content) VALUES (%s, %s, %s)",
                (qid, lab, f"x{lab}"),
            )
    db.commit()

    u = make_user()
    r = client.post(
        "/api/v1/exams/generate",
        json={"level": "N1", "categories": ["text_grammar", "kanji_reading"], "total_questions": 2},
        headers=u["headers"],
    )
    assert r.status_code == 201
    body = r.json()
    assert body["total"] == 4               # 3 空 + 1 单选
    assert len(body["items"]) == 2          # 两张卡片
    all_nos = [q["no"] for it in body["items"] for q in it["questions"]]
    assert sorted(all_nos) == [1, 2, 3, 4]  # 全局题号连续无重复
