"""试卷 Markdown 导出的标记翻译测试。

`question_groups.article` 存的是带语义标记的半成品（规范见 docs/article-format.md），
前端由 `renderArticle()` 翻成 HTML。导出走 Markdown，需要一套等价映射——否则
【U】【BOX】<table> 等标记会原样漏进下载的文件里（实际发生过）。
"""
import re

import pytest

from backend.api.exam_export import _render_article, _table_to_markdown

MARKER_RE = re.compile(r"【/?(?:U|BOX|文章[AB])】")
ENTITY_RE = re.compile(r"&(?:lt|gt|amp|nbsp|quot|#\d+);")


def _assert_clean(md: str):
    """产出里不该再有任何未翻译的标记、裸 HTML 或哨兵。"""
    assert not MARKER_RE.search(md), f"标记残留：{md!r}"
    assert "<table" not in md and "</table>" not in md, f"裸 table 残留：{md!r}"
    assert not ENTITY_RE.search(md), f"HTML 实体未还原：{md!r}"
    assert "\x00" not in md, f"哨兵残留：{md!r}"


def test_underline_marker_becomes_u_tag():
    md = _render_article("次の【U】下線部【/U】について答えなさい。")
    assert "<u>下線部</u>" in md
    _assert_clean(md)


def test_box_marker_becomes_quote_block():
    md = _render_article("【BOX】\n募集要項\n応募期間：1月10日\n【/BOX】")
    assert "> 募集要項" in md
    assert "> 応募期間：1月10日" in md
    _assert_clean(md)


def test_article_labels_become_headings():
    md = _render_article("【文章A】\n本文A\n【文章B】\n本文B")
    assert "**文章A**" in md and "**文章B**" in md
    _assert_clean(md)


def test_html_entities_are_unescaped():
    """源站的 &gt; 等实体在 Markdown 里没有解析器，必须还原成字面字符。"""
    md = _render_article("川村市&gt;レポーター募集 &amp; 応募 &lt;要項&gt;")
    assert md == "川村市>レポーター募集 & 応募 <要項>"
    _assert_clean(md)


def test_unpaired_marker_is_stripped_not_leaked():
    """数据异常导致标记不配对时，去掉标记而不是漏给用户。"""
    md = _render_article("【U】没有闭合的下划线")
    _assert_clean(md)
    assert "没有闭合的下划线" in md


def test_table_with_thead_uses_it_as_header():
    html = (
        "<table><thead><tr><th>名前</th><th>国籍</th></tr></thead>"
        "<tbody><tr><td>キム</td><td>韓国</td></tr></tbody></table>"
    )
    md = _table_to_markdown(html)
    lines = md.splitlines()
    assert lines[0] == "| 名前 | 国籍 |"
    assert set(lines[1].replace(" ", "").strip("|").split("|")) == {"---"}
    assert lines[2] == "| キム | 韓国 |"


def test_table_without_thead_keeps_first_row_as_data():
    """无 thead 时不能挪用首行数据当列名，否则那行数据会错位成表头。"""
    html = "<table><tbody><tr><td>日</td><td>行事名</td></tr><tr><td>9月19日</td><td>説明会</td></tr></tbody></table>"
    md = _table_to_markdown(html)
    lines = md.splitlines()
    assert lines[0] == "|  |  |", "应使用空表头占位"
    assert "| 日 | 行事名 |" in lines, "首行数据被吞掉了"
    assert "| 9月19日 | 説明会 |" in lines


def test_table_cell_newline_and_pipe_are_safe():
    """格内 <br> 转空格、内容里的 | 需转义，否则会破坏表格列结构。"""
    html = "<table><tbody><tr><td>一行<br>二行</td><td>a|b</td></tr></tbody></table>"
    md = _table_to_markdown(html)
    assert "一行 二行" in md
    assert r"a\|b" in md
    # 各行列数应一致。只数未转义的 | ——转义过的 \| 是单元格内容，不是列分隔符。
    sep_re = re.compile(r"(?<!\\)\|")
    counts = {len(sep_re.findall(ln)) for ln in md.splitlines() if ln.startswith("|")}
    assert len(counts) == 1, f"列数不一致：{md!r}"


def test_table_inside_box_is_pulled_out_of_quote():
    """Markdown 表格无法嵌在引用块里渲染，需提到引用块之后单独成块。"""
    html = "<table><tbody><tr><td>a</td><td>b</td></tr></tbody></table>"
    md = _render_article(f"【BOX】\n说明文字\n{html}\n【/BOX】")
    _assert_clean(md)
    assert "> 说明文字" in md
    table_line = next(ln for ln in md.splitlines() if ln.startswith("| a "))
    assert not table_line.startswith(">"), "表格行仍在引用块内，无法渲染成表格"


def test_render_article_handles_none_and_empty():
    assert _render_article(None) == ""
    assert _render_article("") == ""


@pytest.mark.parametrize("category,article,stem", [
    ("info_search", "【BOX】\n案内\n【/BOX】", "この案内の内容と合うものはどれか。"),
    ("reading_mid", "本文です。", "筆者の考えに合うものはどれか。"),
])
def test_export_renders_markers_and_reading_stem(db, make_user, category, article, stem):
    """端到端：导出的 Markdown 不含标记，且阅读题的问句必须出现。

    问句曾因「有 article 就只列选项」的分支而整段缺失，打印出来看不懂在问什么。
    """
    from backend.api.exam_export import render_exam_markdown
    from backend.services.exam_builder import build_exam

    u = make_user()
    with db.cursor() as cur:
        cur.execute(
            """INSERT INTO question_groups
               (type, category, article, level, exam_date, difficulty, knowledge_points, source, source_ref)
               VALUES ('reading', %s, %s, 'N1', '2022-07', 3, '[]', 'tst', %s)""",
            (category, article, f"tst#{category}"),
        )
        gid = cur.lastrowid
        cur.execute(
            "INSERT INTO questions (group_id, seq, content, answer, analysis) VALUES (%s, 1, %s, 'a', %s)",
            (gid, stem, "解析【U】要点【/U】"),
        )
        qid = cur.lastrowid
        for label in ("a", "b", "c", "d"):
            cur.execute(
                "INSERT INTO options (question_id, label, content) VALUES (%s, %s, %s)",
                (qid, label, f"选项{label}"),
            )
        built = build_exam(cur, level="N1", plans=[(category, 1)], user_id=u["id"])
        rendered = render_exam_markdown(cur, built["exam_id"], with_answers=True)
    db.rollback()

    assert rendered is not None
    _, md = rendered
    _assert_clean(md)
    assert stem in md, "阅读题的问句未出现在导出中"
    assert "<u>要点</u>" in md, "解析里的下划线标记未翻译"
