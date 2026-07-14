"""chat_repo 仓储层测试：标题、历史顺序/上限、归属校验、级联删除。"""
from backend.db import chat_repo


def _seed_user(db, email="repo@test.com"):
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO users (email, hashed_password, role) VALUES (%s, 'x', 'student')",
            (email,),
        )
        uid = cur.lastrowid
    db.commit()
    return uid


def test_create_session_title_from_first_message(db):
    uid = _seed_user(db)
    with db.cursor() as cur:
        sid = chat_repo.create_session(cur, uid, first_message="帮我出一道 N1 的语法题目练习一下吧")
        cur.execute("SELECT title FROM chat_sessions WHERE id = %s", (sid,))
        title = cur.fetchone()["title"]
    db.commit()
    # 取前 20 字
    assert title == "帮我出一道 N1 的语法题目练习一下吧"[:20]


def test_create_session_default_title(db):
    uid = _seed_user(db)
    with db.cursor() as cur:
        sid = chat_repo.create_session(cur, uid)
        cur.execute("SELECT title FROM chat_sessions WHERE id = %s", (sid,))
        assert cur.fetchone()["title"] == "新对话"
    db.commit()


def test_load_history_order_and_limit(db):
    uid = _seed_user(db)
    with db.cursor() as cur:
        sid = chat_repo.create_session(cur, uid)
        # 依次追加 5 轮消息
        for i in range(5):
            chat_repo.append_message(cur, sid, "user", f"u{i}")
            chat_repo.append_message(cur, sid, "assistant", f"a{i}")
        db.commit()

        # 取最近 4 条，应为升序的 u3/a3/u4/a4
        recent = chat_repo.load_history(cur, sid, limit=4)
    assert [r["content"] for r in recent] == ["u3", "a3", "u4", "a4"]


def test_append_message_updates_session_timestamp(db):
    uid = _seed_user(db)
    with db.cursor() as cur:
        sid = chat_repo.create_session(cur, uid)
        db.commit()
        cur.execute("SELECT updated_at FROM chat_sessions WHERE id = %s", (sid,))
        before = cur.fetchone()["updated_at"]
        chat_repo.append_message(cur, sid, "user", "hi")
        db.commit()
        cur.execute("SELECT updated_at FROM chat_sessions WHERE id = %s", (sid,))
        after = cur.fetchone()["updated_at"]
    assert after >= before


def test_owns_session(db):
    a = _seed_user(db, "a@test.com")
    b = _seed_user(db, "b@test.com")
    with db.cursor() as cur:
        sid = chat_repo.create_session(cur, a)
        db.commit()
        assert chat_repo.owns_session(cur, sid, a) is True
        assert chat_repo.owns_session(cur, sid, b) is False


def test_get_messages_ownership(db):
    a = _seed_user(db, "a@test.com")
    b = _seed_user(db, "b@test.com")
    with db.cursor() as cur:
        sid = chat_repo.create_session(cur, a)
        chat_repo.append_message(cur, sid, "user", "hi")
        db.commit()
        assert chat_repo.get_messages(cur, sid, a) is not None
        assert chat_repo.get_messages(cur, sid, b) is None  # 越权返回 None


def test_delete_session_cascades_messages(db):
    """删除会话应通过外键 CASCADE 连带删除消息（验证测试库保留了 FK）。"""
    uid = _seed_user(db)
    with db.cursor() as cur:
        sid = chat_repo.create_session(cur, uid)
        chat_repo.append_message(cur, sid, "user", "hi")
        chat_repo.append_message(cur, sid, "assistant", "hello")
        db.commit()

        assert chat_repo.delete_session(cur, sid, uid) is True
        db.commit()
        cur.execute("SELECT COUNT(*) AS n FROM chat_messages WHERE session_id = %s", (sid,))
        assert cur.fetchone()["n"] == 0


def test_delete_session_wrong_user_noop(db):
    a = _seed_user(db, "a@test.com")
    b = _seed_user(db, "b@test.com")
    with db.cursor() as cur:
        sid = chat_repo.create_session(cur, a)
        db.commit()
        assert chat_repo.delete_session(cur, sid, b) is False  # 非属主删不掉
        assert chat_repo.owns_session(cur, sid, a) is True
