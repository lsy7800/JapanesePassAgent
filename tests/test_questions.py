"""题库读接口冒烟测试：筛选与题组详情。"""
import pytest


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


def test_list_questions_all(client, seed_questions):
    r = client.get("/api/v1/questions")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2
    assert len(body["items"]) == 2


def test_list_questions_filter_by_level(client, seed_questions):
    r = client.get("/api/v1/questions", params={"level": "N1"})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["level"] == "N1"


def test_list_questions_filter_by_category(client, seed_questions):
    r = client.get("/api/v1/questions", params={"category": "context"})
    assert r.status_code == 200
    assert body_levels(r) == ["N2"]


def test_list_questions_empty(client):
    r = client.get("/api/v1/questions", params={"level": "N5"})
    assert r.status_code == 200
    assert r.json()["total"] == 0


def test_get_group_detail(client, seed_questions):
    gid = next(iter(seed_questions))
    r = client.get(f"/api/v1/questions/{gid}")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == gid
    assert len(body["questions"]) == 1
    assert len(body["questions"][0]["options"]) == 4


def test_get_group_not_found(client):
    assert client.get("/api/v1/questions/999999").status_code == 404


def body_levels(resp):
    return [it["level"] for it in resp.json()["items"]]
