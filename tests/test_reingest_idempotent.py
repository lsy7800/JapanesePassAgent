"""重新入库的幂等性与历史试卷安全性测试。

回归背景：入库原先是「按 source 删掉所有题组再重建」，而 exam_items.group_id 的
外键是 ON DELETE CASCADE——每次重跑入库都会连带删掉引用这些题目的作答记录，历史
试卷变成空壳或缺题（实际发生过：29 张试卷被打穿）。改成按 source_ref upsert 后
题组 id 保持稳定，本文件锁住这个行为。
"""
import json

import pytest

from crawler.spiders import write_to_mysql as w


@pytest.fixture
def passage_file(tmp_path):
    """造一个「一篇 2 问」的阅读源文件，返回 (路径, 数据)。"""
    data = [{
        "id": 1,
        "date": "2020-07-N1",
        "level": "N1",
        "article": "原始文章",
        "questions": [
            {"no": 1, "question": "问一", "options": {"a": "A1", "b": "B1", "c": "C1", "d": "D1"},
             "answer": "a", "analysis": "解析一", "difficulty": "5", "knowledge_points": ["细节理解"]},
            {"no": 2, "question": "问二", "options": {"a": "A2", "b": "B2", "c": "C2", "d": "D2"},
             "answer": "b", "analysis": "解析二", "difficulty": "5", "knowledge_points": ["主旨理解"]},
        ],
    }]
    p = tmp_path / "reingest_src.json"
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return p, data


def _ingest(path, source="reingest_src"):
    w._write_passages(str(path), source=source, category="reading_mid",
                      group_type="reading", normalize=None)


def _fresh(db):
    """开启新的读快照。

    入库函数用自己的连接提交，而本连接在 REPEATABLE READ 下沿用旧快照，
    不 rollback 就读不到刚写入的数据（读到的是入库前的旧值）。
    """
    db.rollback()


def _group(db, source_ref="reingest_src#1"):
    _fresh(db)
    with db.cursor() as cur:
        cur.execute("SELECT * FROM question_groups WHERE source_ref = %s", (source_ref,))
        return cur.fetchone()


def test_reingest_keeps_group_id_and_updates_content(db, passage_file):
    """重复入库：题组 id 不变，内容按源文件更新。"""
    path, data = passage_file
    _ingest(path)
    first = _group(db)
    assert first["article"] == "原始文章"

    # 改文章后重新入库
    data[0]["article"] = "修订后的文章"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    _ingest(path)

    second = _group(db)
    assert second["id"] == first["id"], "题组 id 变了，会打穿引用它的历史试卷"
    assert second["article"] == "修订后的文章", "内容未更新"

    # 子题与选项没有被重复插入
    _fresh(db)
    with db.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS n FROM questions WHERE group_id = %s", (first["id"],))
        assert cur.fetchone()["n"] == 2
        cur.execute("""SELECT COUNT(*) AS n FROM options o JOIN questions q ON o.question_id = q.id
                       WHERE q.group_id = %s""", (first["id"],))
        assert cur.fetchone()["n"] == 8


def test_reingest_preserves_exam_answers(db, make_user, passage_file):
    """核心回归：重新入库不得破坏引用该题组的试卷与作答记录。"""
    path, data = passage_file
    _ingest(path)
    gid = _group(db)["id"]
    u = make_user()

    # 造一张已提交试卷，引用该题组的两个子题，并写入作答
    with db.cursor() as cur:
        cur.execute("""INSERT INTO exams (user_id, level, total, score, status)
                       VALUES (%s, 'N1', 2, 1, 'submitted')""", (u["id"],))
        exam_id = cur.lastrowid
        for seq, (sub, ans, ok) in enumerate([(1, "a", 1), (2, "c", 0)], 1):
            cur.execute("""INSERT INTO exam_items (exam_id, seq, group_id, sub_seq, user_answer, is_correct)
                           VALUES (%s, %s, %s, %s, %s, %s)""", (exam_id, seq, gid, sub, ans, ok))
    db.commit()

    # 改内容后重新入库
    data[0]["article"] = "改过的文章"
    data[0]["questions"][0]["analysis"] = "改过的解析"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    _ingest(path)

    _fresh(db)
    with db.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS n FROM exams WHERE id = %s", (exam_id,))
        assert cur.fetchone()["n"] == 1, "试卷被删了"
        cur.execute("""SELECT seq, user_answer, is_correct FROM exam_items
                       WHERE exam_id = %s ORDER BY seq""", (exam_id,))
        items = cur.fetchall()
    assert len(items) == 2, "作答记录被级联删除了"
    assert [i["user_answer"] for i in items] == ["a", "c"], "作答内容被改动"
    assert [i["is_correct"] for i in items] == [1, 0], "判分结果被改动"

    # 题目内容确实更新了
    assert _group(db)["article"] == "改过的文章"
    with db.cursor() as cur:
        cur.execute("SELECT analysis FROM questions WHERE group_id = %s AND seq = 1", (gid,))
        assert cur.fetchone()["analysis"] == "改过的解析"


def test_reingest_prunes_removed_subquestions(db, passage_file):
    """源数据删掉一个子题：该子题及其选项应被清理，不留残留。"""
    path, data = passage_file
    _ingest(path)
    gid = _group(db)["id"]

    data[0]["questions"] = data[0]["questions"][:1]  # 只留第 1 问
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    _ingest(path)

    _fresh(db)
    with db.cursor() as cur:
        cur.execute("SELECT seq FROM questions WHERE group_id = %s ORDER BY seq", (gid,))
        assert [r["seq"] for r in cur.fetchall()] == [1]
        cur.execute("""SELECT COUNT(*) AS n FROM options o JOIN questions q ON o.question_id = q.id
                       WHERE q.group_id = %s""", (gid,))
        assert cur.fetchone()["n"] == 4, "被删子题的选项没清理干净"


def test_reingest_prunes_removed_groups(db, passage_file):
    """源数据整篇消失：该题组应被删除（题目确实没了，不该留着）。"""
    path, data = passage_file
    data.append({**data[0], "id": 2, "article": "第二篇"})
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    _ingest(path)
    assert _group(db, "reingest_src#2") is not None

    del data[1]  # 删掉第二篇
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    _ingest(path)

    assert _group(db, "reingest_src#1") is not None, "还在源数据里的题组被误删"
    assert _group(db, "reingest_src#2") is None, "已消失的题组未清理"


def test_wrong_ingest_function_does_not_wipe_subquestions(db, tmp_path):
    """用错入库函数（扁平结构喂给嵌套路径）必须报错，而非静默清空子题。

    实际踩过：把扁平的听力文件喂给 write_listening_passage_to_mysql，它找不到
    questions 键 → 解析出 0 个子题 → 清空了该题组已有的全部子题与选项。
    """
    flat = [{
        "id": 1, "date": "2017-12-N1", "audio_url": "mp3/x.mp3",
        "article": "听力脚本", "question": "", "choice": ["A", "B", "C", "D"],
        "answer": "3", "analysis": "解析",
    }]
    p = tmp_path / "flat_listening.json"
    p.write_text(json.dumps(flat, ensure_ascii=False), encoding="utf-8")

    # 先用正确的扁平路径入库
    w.write_listening_to_mysql(str(p), source="flat_src", category="integ_listen")
    _fresh(db)
    with db.cursor() as cur:
        cur.execute("""SELECT COUNT(*) AS n FROM options o JOIN questions q ON o.question_id = q.id
                       JOIN question_groups g ON q.group_id = g.id WHERE g.source = 'flat_src'""")
        assert cur.fetchone()["n"] == 4

    # 再故意用错函数：嵌套路径找不到 questions 键 → 应抛错，而非清空既有子题
    with db.cursor() as cur:
        with pytest.raises(ValueError, match="拒绝清空既有子题"):
            w._insert_listening_passage(cur, flat[0], "flat_src", "integ_listen")
    db.rollback()

    # 子题与选项都还在
    _fresh(db)
    with db.cursor() as cur:
        cur.execute("""SELECT COUNT(*) AS n FROM options o JOIN questions q ON o.question_id = q.id
                       JOIN question_groups g ON q.group_id = g.id WHERE g.source = 'flat_src'""")
        assert cur.fetchone()["n"] == 4, "用错函数把选项清空了"


def test_reingest_skips_prune_on_partial_failure(db, passage_file, monkeypatch):
    """有记录写入失败时跳过清理：否则会把「只是这次写失败」的题组误删。"""
    path, data = passage_file
    data.append({**data[0], "id": 2, "article": "第二篇"})
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    _ingest(path)

    real = w._insert_passage

    def flaky(cursor, passage, source, category, group_type):
        if passage.get("id") == 2:
            raise RuntimeError("模拟写入失败")
        return real(cursor, passage, source, category, group_type)

    monkeypatch.setattr(w, "_insert_passage", flaky)
    _ingest(path)

    # #2 这次没写成功，但它仍在源数据里，不该被当作「已消失」删掉
    assert _group(db, "reingest_src#2") is not None, "写失败的题组被误删"
