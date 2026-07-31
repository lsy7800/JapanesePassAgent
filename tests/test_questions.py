"""题库读接口冒烟测试：筛选、题组详情与鉴权。"""
import pytest


@pytest.fixture
def admin(make_user):
    """题库读接口均限定 admin，测试统一用这个身份。"""
    return make_user(email="admin@test.com", role="admin")


@pytest.fixture
def seed_questions(db):
    """插入两组不同级别/题型的题目，返回 {group_id: level}。"""
    ids = {}
    with db.cursor() as cur:
        for level, category in [("N1", "kanji_reading"), ("N2", "context")]:
            cur.execute(
                "INSERT INTO question_groups (type, category, level, difficulty) "
                "VALUES ('single_choice', %s, %s, 3)",
                (category, level),
            )
            gid = cur.lastrowid
            cur.execute(
                "INSERT INTO questions (group_id, seq, content, answer) "
                "VALUES (%s, 1, %s, 'a')",
                (gid, f"{level} 测试题干"),
            )
            qid = cur.lastrowid
            for label in ("a", "b", "c", "d"):
                cur.execute(
                    "INSERT INTO options (question_id, label, content) VALUES (%s, %s, %s)",
                    (qid, label, f"选项{label}"),
                )
            ids[gid] = level
    db.commit()
    return ids


def test_list_questions_all(client, seed_questions, admin):
    r = client.get("/api/v1/questions", headers=admin["headers"])
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2
    assert len(body["items"]) == 2


def test_list_questions_filter_by_level(client, seed_questions, admin):
    r = client.get(
        "/api/v1/questions", params={"level": "N1"}, headers=admin["headers"]
    )
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["level"] == "N1"


def test_list_questions_filter_by_category(client, seed_questions, admin):
    r = client.get(
        "/api/v1/questions", params={"category": "context"}, headers=admin["headers"]
    )
    assert r.status_code == 200
    assert body_levels(r) == ["N2"]


def test_list_questions_empty(client, admin):
    r = client.get(
        "/api/v1/questions", params={"level": "N5"}, headers=admin["headers"]
    )
    assert r.status_code == 200
    assert r.json()["total"] == 0


def test_get_group_detail(client, seed_questions, admin):
    gid = next(iter(seed_questions))
    r = client.get(f"/api/v1/questions/{gid}", headers=admin["headers"])
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == gid
    assert len(body["questions"]) == 1
    assert len(body["questions"][0]["options"]) == 4


def test_get_group_not_found(client, admin):
    r = client.get("/api/v1/questions/999999", headers=admin["headers"])
    assert r.status_code == 404


# ---------- 鉴权：题组详情含 answer/analysis，绝不能对学生开放 ----------
# 曾经这四个读接口都没有鉴权，学生考试中开新标签访问
# /api/v1/questions/{id} 就能直接读到 answer。


def test_group_detail_requires_auth(client, seed_questions):
    gid = next(iter(seed_questions))
    assert client.get(f"/api/v1/questions/{gid}").status_code == 401


def test_group_detail_forbidden_for_student(client, seed_questions, make_user):
    gid = next(iter(seed_questions))
    student = make_user(email="cheater@test.com", role="student")
    r = client.get(f"/api/v1/questions/{gid}", headers=student["headers"])
    assert r.status_code == 403
    # 连带确认答案没有随 403 的响应体漏出
    assert "answer" not in r.text


def test_list_questions_requires_admin(client, make_user):
    assert client.get("/api/v1/questions").status_code == 401
    student = make_user(email="s2@test.com", role="student")
    r = client.get("/api/v1/questions", headers=student["headers"])
    assert r.status_code == 403


def test_sources_requires_admin(client, make_user):
    assert client.get("/api/v1/sources").status_code == 401
    student = make_user(email="s3@test.com", role="student")
    assert client.get("/api/v1/sources", headers=student["headers"]).status_code == 403


def test_categories_requires_login_but_allows_student(client, make_user):
    """/categories 是级别→题型联动元数据，学生端要用，只要求登录。"""
    assert client.get("/api/v1/categories").status_code == 401
    student = make_user(email="s4@test.com", role="student")
    r = client.get("/api/v1/categories", headers=student["headers"])
    assert r.status_code == 200
    assert len(r.json()["items"]) > 0


def body_levels(resp):
    return [it["level"] for it in resp.json()["items"]]
