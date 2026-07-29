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
    """替换编排层引用的 plan_exam（同步与 SSE 路径共用）。capture 用于记录调用参数。"""
    def fake_plan(requirement, weak_points, level, available_categories):
        if capture is not None:
            capture["requirement"] = requirement
            capture["weak_points"] = weak_points
            capture["level"] = level
        return plan
    monkeypatch.setattr("backend.services.smart_exam.plan_exam", fake_plan)


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
    # 试卷不含答案（嵌套子题结构）
    first = body["items"][0]
    sub = first["questions"][0]
    assert "answer" not in sub and "correct_answer" not in sub
    assert len(sub["options"]) == 4


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
    # 可提交判分（作答键为子题全局题号 no）
    answers = [{"seq": q["no"], "answer": "a"} for it in r.json()["items"] for q in it["questions"]]
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


# ========== SSE 阶段化组卷 ==========

def _sse_events(text: str) -> list[dict]:
    """把 SSE 响应体解析成事件 dict 列表。"""
    import json
    out = []
    for line in text.splitlines():
        if line.startswith("data: "):
            out.append(json.loads(line[6:]))
    return out


def test_smart_stream_emits_stages_and_exam_id(client, make_user, seed_bank, monkeypatch):
    """SSE 应按序推出各阶段，方案阶段带 rationale，最后 done 给出可用 exam_id。"""
    u = make_user()
    _patch_plan(monkeypatch, {
        "level": "N1",
        "category_quotas": {"kanji_reading": 3, "context": 2},
        "total_questions": 10,
        "difficulty_min": None, "difficulty_max": None,
        "rationale": "针对你的薄弱点组卷。",
    })
    r = client.get(
        "/api/v1/exams/smart-generate/stream",
        params={"requirement": "针对薄弱点出题", "level": "N1", "token": u["token"]},
    )
    assert r.status_code == 200
    events = _sse_events(r.text)

    # 阶段顺序：weak → weak_done → plan(stage) → plan(方案) → build → done
    assert [e.get("key") for e in events if e["type"] == "stage"] == [
        "weak", "weak_done", "plan", "build",
    ]

    plan_ev = next(e for e in events if e["type"] == "plan")
    assert plan_ev["rationale"] == "针对你的薄弱点组卷。"
    # 方案摘要含题型中文名与题量，供前端直接展示
    assert "3 题" in plan_ev["summary"] and "2 题" in plan_ev["summary"]

    done = next(e for e in events if e["type"] == "done")
    assert done["groups"] == 5  # 题组数（本例每组一问，故与题量相等）
    assert done["rationale"] == "针对你的薄弱点组卷。"

    # done 给的 exam_id 可直接取卷（走既有归属校验的 GET 接口）
    exam = client.get(f"/api/v1/exams/{done['exam_id']}", headers=u["headers"])
    assert exam.status_code == 200
    assert exam.json()["total"] == 5


def test_smart_stream_cold_start_message(client, make_user, seed_bank, monkeypatch):
    """无历史错题：weak_done 阶段应说明将均衡出题，而非报错。"""
    u = make_user()
    _patch_plan(monkeypatch, {
        "level": "N1", "category_quotas": None, "total_questions": 3,
        "difficulty_min": None, "difficulty_max": None, "rationale": "均衡出题。",
    })
    r = client.get(
        "/api/v1/exams/smart-generate/stream",
        params={"requirement": "帮我练练", "level": "N1", "token": u["token"]},
    )
    events = _sse_events(r.text)
    weak_done = next(e for e in events if e.get("key") == "weak_done")
    assert weak_done["weak_count"] == 0
    assert "暂无历史" in weak_done["message"]
    assert any(e["type"] == "done" for e in events)


def test_smart_stream_empty_pool_emits_error(client, make_user, seed_bank, monkeypatch):
    """题池为空：以 error 事件收尾（code=no_questions），不抛 500。"""
    u = make_user()
    _patch_plan(monkeypatch, {
        "level": "N5", "category_quotas": None, "total_questions": 5,
        "difficulty_min": None, "difficulty_max": None, "rationale": "x",
    })
    r = client.get(
        "/api/v1/exams/smart-generate/stream",
        params={"requirement": "出题", "level": "N5", "token": u["token"]},
    )
    assert r.status_code == 200  # SSE 已建立，错误在流内表达
    events = _sse_events(r.text)
    err = next(e for e in events if e["type"] == "error")
    assert err["code"] == "no_questions"
    assert not any(e["type"] == "done" for e in events)


def test_smart_stream_planner_failure_falls_back(client, make_user, seed_bank, monkeypatch):
    """规划器内部异常已自兜底为默认方案，流程仍应正常出卷。"""
    u = make_user()

    def boom(*a, **kw):
        raise RuntimeError("DeepSeek 掛了")
    # 打在真实规划器依赖的 _llm 上，验证 plan_exam 的兜底分支
    monkeypatch.setattr("backend.agent.tools._llm", boom)

    r = client.get(
        "/api/v1/exams/smart-generate/stream",
        params={"requirement": "出题", "level": "N1", "token": u["token"]},
    )
    events = _sse_events(r.text)
    done = next(e for e in events if e["type"] == "done")
    assert done["groups"] > 0
    assert "暂时不可用" in done["rationale"]  # 兜底文案


def test_smart_stream_requires_token(client):
    r = client.get("/api/v1/exams/smart-generate/stream", params={"requirement": "x"})
    assert r.status_code == 401
