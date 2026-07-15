"""按整场考试（年月）智能组卷测试：monkeypatch 规划器返回带 exam_date/whole_exam 的方案。"""
import pytest


@pytest.fixture
def seed_dated_bank(db):
    """播种两场考试的题目：2010-07 共 8 组（grammar_form 5 + context 3），2013-12 共 4 组。"""
    def add(category, exam_date, n):
        gids = []
        with db.cursor() as cur:
            for i in range(n):
                cur.execute(
                    "INSERT INTO question_groups (type, category, level, exam_date, difficulty) "
                    "VALUES ('single_choice', %s, 'N1', %s, 3)",
                    (category, exam_date),
                )
                gid = cur.lastrowid
                cur.execute(
                    "INSERT INTO questions (group_id, seq, content, answer) VALUES (%s, 1, %s, 'a')",
                    (gid, f"{category}-{exam_date}-{i}"),
                )
                qid = cur.lastrowid
                for lab in ("a", "b", "c", "d"):
                    cur.execute(
                        "INSERT INTO options (question_id, label, content) VALUES (%s, %s, %s)",
                        (qid, lab, f"opt{lab}"),
                    )
                gids.append(gid)
        db.commit()
        return gids

    return {
        "2010-07-grammar": add("grammar_form", "2010-07-N1（1）", 5),
        "2010-07-context": add("context", "2010-07", 3),
        "2013-12": add("grammar_form", "2013-12-N1", 4),
    }


def _patch_plan(monkeypatch, plan):
    monkeypatch.setattr(
        "backend.api.routers.exams.plan_exam",
        lambda requirement, weak_points, level, available_categories: plan,
    )


def _whole_plan(**over):
    base = {
        "level": "N1", "category_quotas": None, "total_questions": 300,
        "difficulty_min": None, "difficulty_max": None,
        "exam_date": "2010-07", "whole_exam": True, "rationale": "2010年7月整套真题。",
    }
    base.update(over)
    return base


def test_whole_exam_pulls_all_of_that_date(client, make_user, seed_dated_bank, monkeypatch):
    """整场组卷：2010-07 的全部 8 组题都进卷，不被 50 上限或默认 10 砍。"""
    u = make_user()
    _patch_plan(monkeypatch, _whole_plan())
    r = client.post(
        "/api/v1/exams/smart-generate",
        json={"requirement": "帮我组2010年7月的所有题目", "level": "N1"},
        headers=u["headers"],
    )
    assert r.status_code == 201
    body = r.json()
    assert body["total"] == 8            # 5 + 3，全部 2010-07 题组
    assert len(body["items"]) == 8


def test_whole_exam_excludes_other_dates(client, make_user, seed_dated_bank, monkeypatch):
    """整场组卷只含指定年月：2013-12 的题不混进 2010-07 的卷。"""
    u = make_user()
    _patch_plan(monkeypatch, _whole_plan())
    r = client.post(
        "/api/v1/exams/smart-generate",
        json={"requirement": "2010年7月全部", "level": "N1"},
        headers=u["headers"],
    )
    assert r.json()["total"] == 8  # 不含 2013-12 的 4 组


def test_date_plus_category(client, make_user, seed_dated_bank, monkeypatch):
    """日期叠加题型：2010年7月的语法题 → 只出该场 grammar_form 5 组。"""
    u = make_user()
    _patch_plan(monkeypatch, _whole_plan(
        category_quotas={"grammar_form": 50}, whole_exam=False, total_questions=50,
    ))
    r = client.post(
        "/api/v1/exams/smart-generate",
        json={"requirement": "2010年7月的语法题", "level": "N1"},
        headers=u["headers"],
    )
    body = r.json()
    assert body["total"] == 5  # 2010-07 的 grammar_form 恰好 5 组


def test_whole_exam_gradable(client, make_user, seed_dated_bank, monkeypatch):
    """整场卷可正常提交判分（全局题号连续）。"""
    u = make_user()
    _patch_plan(monkeypatch, _whole_plan())
    r = client.post(
        "/api/v1/exams/smart-generate",
        json={"requirement": "2010年7月整套", "level": "N1"},
        headers=u["headers"],
    )
    exam_id = r.json()["id"]
    answers = [{"seq": q["no"], "answer": "a"} for it in r.json()["items"] for q in it["questions"]]
    sr = client.post(f"/api/v1/exams/{exam_id}/submit", json={"answers": answers}, headers=u["headers"])
    assert sr.status_code == 200
    assert sr.json()["score"] == 8  # 全选 a，题库答案都是 a
