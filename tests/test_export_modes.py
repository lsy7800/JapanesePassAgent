"""试卷导出的三种模式测试。

背景：导出原先只有 with_answers 布尔开关（题目卷 / 题目+答案两种）。用户说「再给我
一份答案」时，「只有答案」这一份在系统里不存在，模型只能退而导出两份都含答案的卷，
于是聊天里冒出两个看起来一样的下载按钮。现补 answers_only 模式。
"""
import pytest

from backend.api.exam_export import (
    MODE_ANSWERS_ONLY,
    MODE_QUESTIONS,
    MODE_WITH_ANSWERS,
    render_exam_markdown,
)
from backend.services.exam_builder import build_exam


@pytest.fixture
def exam(db, make_user):
    """播种一张 2 题的卷（含解析），返回 (exam_id, user)。"""
    u = make_user()
    with db.cursor() as cur:
        for i in range(2):
            cur.execute(
                """INSERT INTO question_groups
                   (type, category, level, exam_date, difficulty, knowledge_points, source, source_ref)
                   VALUES ('single_choice', 'kanji_reading', 'N1', '2022-07', 3, '[]', 'tst', %s)""",
                (f"tst#{i}",),
            )
            gid = cur.lastrowid
            cur.execute(
                "INSERT INTO questions (group_id, seq, content, answer, analysis) "
                "VALUES (%s, 1, %s, 'b', %s)",
                (gid, f"题干{i}", f"解析{i}"),
            )
            qid = cur.lastrowid
            for label in ("a", "b", "c", "d"):
                cur.execute(
                    "INSERT INTO options (question_id, label, content) VALUES (%s, %s, %s)",
                    (qid, label, f"选项{label}"),
                )
        built = build_exam(cur, level="N1", plans=[("kanji_reading", 2)], user_id=u["id"])
    db.commit()
    return built["exam_id"], u


def _render(db, exam_id, **kw):
    with db.cursor() as cur:
        return render_exam_markdown(cur, exam_id, **kw)


def test_questions_mode_has_options_no_answers(db, exam):
    exam_id, _ = exam
    fn, md = _render(db, exam_id, mode=MODE_QUESTIONS)
    assert "- B. 选项b" in md, "缺少选项"
    assert "正确答案" not in md, "题目卷不应含答案"
    assert "解析0" not in md
    assert fn == f"JLPT_N1_exam_{exam_id}.md"


def test_with_answers_mode_has_both(db, exam):
    exam_id, _ = exam
    fn, md = _render(db, exam_id, mode=MODE_WITH_ANSWERS)
    assert "- B. 选项b" in md, "缺少题目"
    assert "正确答案：**B**" in md, "缺少答案"
    assert "解析0" in md and "解析1" in md
    assert fn.endswith("_答案.md")


def test_answers_only_mode_has_answers_without_questions(db, exam):
    """核心：只有答案，不含题目与选项——这正是此前缺失的那一份。"""
    exam_id, _ = exam
    fn, md = _render(db, exam_id, mode=MODE_ANSWERS_ONLY)
    assert "正确答案：**B**" in md
    assert "解析0" in md and "解析1" in md
    assert "- B. 选项b" not in md, "仅答案模式不应含选项"
    assert "题干0" not in md, "仅答案模式不应含题干"
    # 不是用来作答的，不需要姓名/得分栏
    assert "姓名" not in md
    assert fn.endswith("_仅答案.md")


def test_three_modes_produce_distinct_filenames(db, exam):
    """三份文件名必须不同，否则同时下载会互相覆盖。"""
    exam_id, _ = exam
    names = {
        m: _render(db, exam_id, mode=m)[0]
        for m in (MODE_QUESTIONS, MODE_WITH_ANSWERS, MODE_ANSWERS_ONLY)
    }
    assert len(set(names.values())) == 3, f"文件名重复：{names}"


def test_with_answers_bool_stays_backward_compatible(db, exam):
    """旧调用（只传 with_answers）行为不变。"""
    exam_id, _ = exam
    _, md_false = _render(db, exam_id, with_answers=False)
    _, md_true = _render(db, exam_id, with_answers=True)
    assert "正确答案" not in md_false
    assert "正确答案" in md_true
    # 与显式 mode 等价
    assert md_false == _render(db, exam_id, mode=MODE_QUESTIONS)[1]
    assert md_true == _render(db, exam_id, mode=MODE_WITH_ANSWERS)[1]


def test_unknown_mode_raises(db, exam):
    exam_id, _ = exam
    with pytest.raises(ValueError, match="未知导出模式"):
        _render(db, exam_id, mode="bogus")


# ========== HTTP 端点 ==========

@pytest.mark.parametrize("mode,expect_opt,expect_ans", [
    ("questions", True, False),
    ("with_answers", True, True),
    ("answers_only", False, True),
])
def test_export_endpoint_modes(client, db, exam, mode, expect_opt, expect_ans):
    exam_id, u = exam
    r = client.get(
        f"/api/v1/exams/{exam_id}/export",
        params={"format": "markdown", "mode": mode},
        headers=u["headers"],
    )
    assert r.status_code == 200
    body = r.content.decode()
    assert ("- B. 选项b" in body) is expect_opt
    assert ("正确答案" in body) is expect_ans


def test_export_endpoint_rejects_bad_mode(client, exam):
    exam_id, u = exam
    r = client.get(
        f"/api/v1/exams/{exam_id}/export",
        params={"format": "markdown", "mode": "bogus"},
        headers=u["headers"],
    )
    assert r.status_code == 400
    assert "未知导出模式" in r.json()["detail"]


# ========== Agent 工具 ==========

def test_export_tool_accepts_three_modes(exam):
    from backend.agent import tools

    exam_id, _ = exam
    for mode in ("questions", "with_answers", "answers_only"):
        r = tools.export_exam.invoke({"exam_id": exam_id, "mode": mode})
        assert r["ok"] is True, r
        assert r["mode"] == mode


def test_export_tool_rejects_bad_mode(exam):
    from backend.agent import tools

    exam_id, _ = exam
    r = tools.export_exam.invoke({"exam_id": exam_id, "mode": "bogus"})
    assert r["ok"] is False
    assert "未知导出模式" in r["message"]


def test_export_tool_reports_missing_exam():
    from backend.agent import tools

    r = tools.export_exam.invoke({"exam_id": 99999999, "mode": "questions"})
    assert r["ok"] is False
    assert "不存在" in r["message"]
