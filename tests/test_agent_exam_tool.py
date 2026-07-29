"""Agent 组卷工具 `tools.generate_exam` 的回归测试。

背景：该工具原先自建了一套抽题 + 落库 SQL（与共享服务 `exam_builder.build_exam` 平行演进），
少了三个能力并写坏数据：
1. 无 exam_date → 无法按场次出真题
2. 无法排除听力 → 听力题混进要打印的笔试卷
3. 写 exam_items 漏 sub_seq → 阅读/完形每篇只登记 1 题，导出静默少题，
   且 exams.total 记的是题组数而非可评分子题数
另外 user_id 交由大模型填，漏填则试卷归属为 NULL、下载必 403。

现已改为委托 build_exam。本文件锁住上述行为，不触达 DeepSeek。
"""
import pytest

from backend.agent import tools


@pytest.fixture
def bank(db):
    """播种题库：两种单选题型 + 一篇多问阅读 + 一道听力，跨两个场次。

    返回 {"single": [gid...], "reading": gid, "listening": gid}
    """
    ids = {"single": [], "reading": None, "listening": None}

    def add_group(gtype, category, date, article=None, audio=None, subs=1):
        with db.cursor() as cur:
            cur.execute(
                """INSERT INTO question_groups
                   (type, category, article, audio_url, level, exam_date, difficulty, knowledge_points, source, source_ref)
                   VALUES (%s, %s, %s, %s, 'N1', %s, 3, '[]', 'tst', %s)""",
                (gtype, category, article, audio, date,
                 f"tst#{gtype}-{category}-{date}-{len(ids['single'])}"),
            )
            gid = cur.lastrowid
            for seq in range(1, subs + 1):
                cur.execute(
                    "INSERT INTO questions (group_id, seq, content, answer) VALUES (%s, %s, %s, 'a')",
                    (gid, seq, f"{category}-{seq} 题干"),
                )
                qid = cur.lastrowid
                for label in ("a", "b", "c", "d"):
                    cur.execute(
                        "INSERT INTO options (question_id, label, content) VALUES (%s, %s, %s)",
                        (qid, label, f"选项{label}"),
                    )
        return gid

    # 2022-07 场次：5 道汉字读音 + 1 篇 3 问阅读 + 1 道听力
    for _ in range(5):
        ids["single"].append(add_group("single_choice", "kanji_reading", "2022-07"))
    ids["reading"] = add_group("reading", "reading_mid", "2022-07-N1（1）",
                               article="文章正文", subs=3)
    ids["listening"] = add_group("listening", "task_listening", "2022-07-N1（1）",
                                 article="听力脚本", audio="mp3/x.mp3")
    # 另一场次，用于验证 exam_date 确实收窄了题池
    add_group("single_choice", "context", "2019-12")
    db.commit()
    return ids


def _call(**kw):
    kw.setdefault("user_id", 1)
    return tools.generate_exam.invoke(kw)


def test_missing_user_id_returns_error_not_orphan_exam(db, bank):
    """缺 user_id 时报错，而非写出一张归属 NULL、无法下载的卷。"""
    r = tools.generate_exam.invoke({"level": "N1", "total_questions": 3})
    assert r["exam_id"] is None
    assert "user_id" in r["message"]
    db.rollback()
    with db.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS n FROM exams WHERE user_id IS NULL")
        assert cur.fetchone()["n"] == 0, "写出了归属为 NULL 的试卷"


def test_multi_subquestion_group_registers_every_subquestion(db, make_user, bank):
    """核心回归：一篇 3 问的阅读必须登记 3 道可评分题，而非 1 道。"""
    u = make_user()
    r = _call(level="N1", category="reading_mid", total_questions=1, user_id=u["id"])

    assert r["total"] == 3, f"3 问的阅读只登记了 {r['total']} 题"
    assert r["groups"] == 1
    assert len(r["items"]) == 3, "items 未逐子题列出"

    db.rollback()
    with db.cursor() as cur:
        cur.execute("SELECT total FROM exams WHERE id = %s", (r["exam_id"],))
        assert cur.fetchone()["total"] == 3, "exams.total 记的不是可评分子题数"
        cur.execute(
            "SELECT sub_seq FROM exam_items WHERE exam_id = %s ORDER BY seq", (r["exam_id"],)
        )
        assert [x["sub_seq"] for x in cur.fetchall()] == [1, 2, 3], "sub_seq 未正确展开"


def test_exam_date_narrows_to_that_session(db, make_user, bank):
    """按 exam_date 组卷：所选题目全部属于该场次。"""
    u = make_user()
    r = _call(level="N1", exam_date="2022-07", whole_exam=True, user_id=u["id"])

    db.rollback()
    with db.cursor() as cur:
        cur.execute(
            """SELECT DISTINCT LEFT(g.exam_date, 7) AS d FROM exam_items ei
               JOIN question_groups g ON g.id = ei.group_id WHERE ei.exam_id = %s""",
            (r["exam_id"],),
        )
        assert [x["d"] for x in cur.fetchall()] == ["2022-07"]


def test_exclude_listening_drops_listening_groups(db, make_user, bank):
    """exclude_listening=True 时结果中不含听力题组。"""
    u = make_user()
    r = _call(level="N1", exam_date="2022-07", whole_exam=True,
              exclude_listening=True, user_id=u["id"])

    db.rollback()
    with db.cursor() as cur:
        cur.execute(
            """SELECT DISTINCT g.type FROM exam_items ei
               JOIN question_groups g ON g.id = ei.group_id WHERE ei.exam_id = %s""",
            (r["exam_id"],),
        )
        types = {x["type"] for x in cur.fetchall()}
    assert "listening" not in types, f"听力未被排除：{types}"
    # 该场非听力：5 道单选 + 1 篇 3 问阅读 = 6 题组 / 8 可评分题
    assert r["groups"] == 6
    assert r["total"] == 8


def test_whole_exam_not_truncated_by_default_limit(db, make_user, bank):
    """whole_exam=True 时不受 total_questions 默认值限制，取该场全部题目。"""
    u = make_user()
    # 不传 total_questions（默认 10），该场非听力有 6 个题组，应全部取到
    r = _call(level="N1", exam_date="2022-07", whole_exam=True,
              exclude_listening=True, user_id=u["id"])
    assert r["groups"] == 6

    # 对照：不开整场模式且限 2 题时，应被限制
    r2 = _call(level="N1", exam_date="2022-07", category="kanji_reading",
               total_questions=2, user_id=u["id"])
    assert r2["groups"] == 2


def test_export_question_count_matches_total(db, make_user, bank):
    """端到端：导出的 Markdown 题目数与 total 一致——锁住「只返回部分内容」。"""
    from backend.api.exam_export import render_exam_markdown

    u = make_user()
    r = _call(level="N1", exam_date="2022-07", whole_exam=True,
              exclude_listening=True, user_id=u["id"])

    db.rollback()
    with db.cursor() as cur:
        rendered = render_exam_markdown(cur, r["exam_id"], with_answers=True)
    assert rendered is not None
    _, md = rendered

    import re
    # 标题形如「**第 3 题**」或多子题的「**第 3–5 题**」，两种都要算进覆盖范围
    covered = {int(x) for x in re.findall(r"\*\*第 (\d+) 题\*\*", md)}
    for a, b in re.findall(r"\*\*第 (\d+)–(\d+) 题\*\*", md):
        covered |= set(range(int(a), int(b) + 1))
    assert covered == set(range(1, r["total"] + 1)), \
        f"导出缺题：期望 1..{r['total']}，实际覆盖 {sorted(covered)}"
    assert f"题目数量：{r['total']} 题" in md
