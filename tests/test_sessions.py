"""会话管理接口测试：列表 / 消息 / 重命名 / 删除，含越权 404。"""
from backend.db import chat_repo


def _make_session(db, user_id, title_msg="你好呀", with_msgs=True):
    """直接经仓储建一个会话，返回 session_id。"""
    with db.cursor() as cur:
        sid = chat_repo.create_session(cur, user_id, first_message=title_msg)
        if with_msgs:
            chat_repo.append_message(cur, sid, "user", "你好呀")
            chat_repo.append_message(cur, sid, "assistant", "你好，有什么可以帮你？")
    db.commit()
    return sid


def test_list_sessions_only_own(client, db, make_user):
    a = make_user(email="a@test.com")
    b = make_user(email="b@test.com")
    _make_session(db, a["id"])
    _make_session(db, a["id"])
    _make_session(db, b["id"])

    r = client.get("/api/v1/sessions", headers=a["headers"])
    assert r.status_code == 200
    assert len(r.json()) == 2  # 只看到自己的两个


def test_list_sessions_requires_auth(client):
    assert client.get("/api/v1/sessions").status_code == 401


def test_get_messages_success(client, db, make_user):
    u = make_user()
    sid = _make_session(db, u["id"])
    r = client.get(f"/api/v1/sessions/{sid}/messages", headers=u["headers"])
    assert r.status_code == 200
    rows = r.json()
    assert [m["role"] for m in rows] == ["user", "assistant"]


def test_get_messages_cross_user_404(client, db, make_user):
    owner = make_user(email="owner@test.com")
    other = make_user(email="other@test.com")
    sid = _make_session(db, owner["id"])
    r = client.get(f"/api/v1/sessions/{sid}/messages", headers=other["headers"])
    assert r.status_code == 404


def test_rename_session(client, db, make_user):
    u = make_user()
    sid = _make_session(db, u["id"])
    r = client.patch(
        f"/api/v1/sessions/{sid}", json={"title": "语法专项"}, headers=u["headers"]
    )
    assert r.status_code == 200
    assert r.json()["title"] == "语法专项"


def test_rename_cross_user_404(client, db, make_user):
    owner = make_user(email="owner@test.com")
    other = make_user(email="other@test.com")
    sid = _make_session(db, owner["id"])
    r = client.patch(
        f"/api/v1/sessions/{sid}", json={"title": "hack"}, headers=other["headers"]
    )
    assert r.status_code == 404


def test_delete_session(client, db, make_user):
    u = make_user()
    sid = _make_session(db, u["id"])
    r = client.delete(f"/api/v1/sessions/{sid}", headers=u["headers"])
    assert r.status_code == 200
    # 再取消息应 404（会话已不存在）
    assert client.get(
        f"/api/v1/sessions/{sid}/messages", headers=u["headers"]
    ).status_code == 404


def test_delete_cross_user_404(client, db, make_user):
    owner = make_user(email="owner@test.com")
    other = make_user(email="other@test.com")
    sid = _make_session(db, owner["id"])
    assert client.delete(
        f"/api/v1/sessions/{sid}", headers=other["headers"]
    ).status_code == 404
    # 属主仍能看到
    assert client.get(
        f"/api/v1/sessions/{sid}/messages", headers=owner["headers"]
    ).status_code == 200


# ========== 清空全部会话 ==========

def test_clear_all_sessions(client, db, make_user):
    u = make_user()
    _make_session(db, u["id"])
    _make_session(db, u["id"])
    _make_session(db, u["id"])

    r = client.delete("/api/v1/sessions", headers=u["headers"])
    assert r.status_code == 200
    assert r.json()["deleted_sessions"] == 3
    assert client.get("/api/v1/sessions", headers=u["headers"]).json() == []


def test_clear_all_only_affects_own_sessions(client, db, make_user):
    """核心安全约束：不能清掉别人的对话。"""
    mine = make_user(email="mine@test.com")
    other = make_user(email="other@test.com")
    _make_session(db, mine["id"])
    other_sid = _make_session(db, other["id"])

    r = client.delete("/api/v1/sessions", headers=mine["headers"])
    assert r.json()["deleted_sessions"] == 1
    # 别人的会话与消息都还在
    assert len(client.get("/api/v1/sessions", headers=other["headers"]).json()) == 1
    assert client.get(
        f"/api/v1/sessions/{other_sid}/messages", headers=other["headers"]
    ).status_code == 200


def test_clear_all_cascades_messages(client, db, make_user):
    """会话删除后消息应被外键级联清理，不留孤儿。"""
    u = make_user()
    sid = _make_session(db, u["id"])
    client.delete("/api/v1/sessions", headers=u["headers"])

    db.rollback()
    with db.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS n FROM chat_messages WHERE session_id = %s", (sid,))
        assert cur.fetchone()["n"] == 0


def test_clear_all_does_not_touch_exams(client, db, make_user):
    """清空对话不该影响考试数据——两者之间没有任何关联。"""
    u = make_user()
    _make_session(db, u["id"])
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO exams (user_id, level, total, status) VALUES (%s,'N1',5,'submitted')",
            (u["id"],),
        )
        exam_id = cur.lastrowid
    db.commit()

    client.delete("/api/v1/sessions", headers=u["headers"])

    db.rollback()
    with db.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS n FROM exams WHERE id = %s", (exam_id,))
        assert cur.fetchone()["n"] == 1, "清空对话竟然删掉了考试记录"


def test_clear_all_empty_is_not_an_error(client, make_user):
    """没有会话时返回 0，而不是报错。"""
    u = make_user()
    r = client.delete("/api/v1/sessions", headers=u["headers"])
    assert r.status_code == 200
    assert r.json()["deleted_sessions"] == 0


def test_clear_all_requires_auth(client):
    assert client.delete("/api/v1/sessions").status_code == 401
