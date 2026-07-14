"""AI 智能组卷接口测试：monkeypatch 掉 LLM 规划器，不触达 DeepSeek。"""
import pytest


@pytest.fixture
def seed_bank(db):
    """播种两种题型、带知识点的题目，返回 {category: [group_id,...]}。"""
    ids = {"kanji_reading": [], "context": []}
    with db.cursor() as cur:
        for category in ("kanji_reading", "context"):
            for i in range(6):
                cur.execute(
                    "INSERT INTO question_groups (type, category, level, difficulty, knowledge_points) "
                    "VALUES ('single_choice', %s, 'N1', 3, %s)",
                    (category, '["条件表达"]' if category == "context" else '["汉字读音"]'),
                )
                gid = cur.lastrowid
                cur.execute(
                    "INSERT INTO questions (group_id, seq, content, answer) VALUES (%s, 1, %s, 'a')",
                    (gid, f"{category}-{i} 题干"),
                )
                qid = cur.lastrowid
                for label in ("a", "b", "c", "d"):
                    cur.execute(
                        "INSERT INTO options (question_id, label, content) VALUES (%s, %s, %s)",
                        (qid, label, f"选项{label}"),
                    )
                ids[category].append(gid)
    db.commit()
    return ids


def _patch_plan(monkeypatch, plan, capture=None):
    """替换 exams 路由里引用的 plan_exam。capture 用于记录调用参数。"""
    def fake_plan(requirement, weak_points, level, available_categories):
        if capture is not None:
            capture["requirement"] = requirement
            capture["weak_points"] = weak_points
            capture["level"] = level
        return plan
    monkeypatch.setattr("backend.api.routers.exams.plan_exam", fake_plan)


def test_smart_generate_with_quotas(client, make_user, seed_bank, monkeypatch):
    u = make_user()
    _patch_plan(monkeypatch, {
        "level": "N1",
        "category_quotas": {"kanji_reading": 3, "context": 2},
        "total_questions": 10,
        "difficulty_min": None,
        "difficulty_max": None,
        "rationale": "针对你的薄弱点组卷。",
    })
    r = client.post(
        "/api/v1/exams/smart-generate",
        json={"requirement": "针对薄弱点出题", "level": "N1", "time_limit_minutes": 20},
        headers=u["headers"],
    )
    assert r.status_code == 201
    body = r.json()
    assert body["total"] == 5  # 3 + 2
    assert len(body["items"]) == 5
    assert body["rationale"] == "针对你的薄弱点组卷。"
    assert body["time_limit"] == 20
    # 试卷不含答案
    first = body["items"][0]
    assert "answer" not in first and "correct_answer" not in first
    assert len(first["options"]) == 4


def test_smart_generate_links_user_and_gradable(client, make_user, seed_bank, monkeypatch, db):
    u = make_user()
    _patch_plan(monkeypatch, {
        "level": "N1", "category_quotas": None, "total_questions": 4,
        "difficulty_min": None, "difficulty_max": None, "rationale": "综合练习。",
    })
    r = client.post(
        "/api/v1/exams/smart-generate",
        json={"requirement": "来一套综合", "level": "N1"},
        headers=u["headers"],
    )
    assert r.status_code == 201
    exam_id = r.json()["id"]
    # 关联到当前用户
    with db.cursor() as cur:
        cur.execute("SELECT user_id FROM exams WHERE id = %s", (exam_id,))
        assert cur.fetchone()["user_id"] == u["id"]
    # 可提交判分
    answers = [{"seq": it["seq"], "answer": "a"} for it in r.json()["items"]]
    sr = client.post(f"/api/v1/exams/{exam_id}/submit", json={"answers": answers}, headers=u["headers"])
    assert sr.status_code == 200
    assert sr.json()["score"] == len(answers)  # 全部选 a，题库答案都是 a


def test_smart_generate_cold_start_no_history(client, make_user, seed_bank, monkeypatch):
    """新用户无历史：plan_exam 收到空 weak_points。"""
    u = make_user()
    cap = {}
    _patch_plan(monkeypatch, {
        "level": "N1", "category_quotas": None, "total_questions": 3,
        "difficulty_min": None, "difficulty_max": None, "rationale": "暂无历史，均衡出题。",
    }, capture=cap)
    r = client.post(
        "/api/v1/exams/smart-generate",
        json={"requirement": "帮我练练", "level": "N1"},
        headers=u["headers"],
    )
    assert r.status_code == 201
    assert cap["weak_points"] == []  # 冷启动
    assert r.json()["total"] == 3


def test_smart_generate_empty_pool_422(client, make_user, seed_bank, monkeypatch):
    """方案指向没有题的级别 → 422。"""
    u = make_user()
    _patch_plan(monkeypatch, {
        "level": "N5", "category_quotas": None, "total_questions": 5,
        "difficulty_min": None, "difficulty_max": None, "rationale": "x",
    })
    r = client.post(
        "/api/v1/exams/smart-generate",
        json={"requirement": "出题", "level": "N5"},
        headers=u["headers"],
    )
    assert r.status_code == 422


def test_smart_generate_requires_auth(client):
    r = client.post("/api/v1/exams/smart-generate", json={"requirement": "x"})
    assert r.status_code == 401
