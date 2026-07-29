"""试卷 Markdown 导出：把已落库的试卷渲染为可下载/打印的 Markdown 文本。

数据来自 exams / exam_items / question_groups / questions / options 五表，
不调用 LLM。生成结构：抬头 → 题目卷（不含答案）→ （可选）答案与解析另起一节。
"""
import re

from backend.config.categories import category_name


def _fetch_export_data(cursor, exam_id: int) -> dict | None:
    """取试卷抬头 + 各卡片（按 group_id 分组：文章 + 子题；子题含题干/选项/答案/解析）。"""
    cursor.execute(
        "SELECT id, level, total, status FROM exams WHERE id = %s",
        (exam_id,),
    )
    exam = cursor.fetchone()
    if exam is None:
        return None

    cursor.execute(
        "SELECT seq, group_id, sub_seq FROM exam_items WHERE exam_id = %s ORDER BY seq",
        (exam_id,),
    )
    rows = cursor.fetchall()

    items: list[dict] = []
    for r in rows:
        # 同题组连续 → 题组变化时开新卡片
        if not items or items[-1]["group_id"] != r["group_id"]:
            cursor.execute(
                "SELECT category, article FROM question_groups WHERE id = %s",
                (r["group_id"],),
            )
            g = cursor.fetchone()
            items.append({
                "group_id": r["group_id"],
                "category": g["category"] if g else None,
                "article": (g["article"] or "") if g else "",
                "questions": [],
            })
        cursor.execute(
            "SELECT id, content, marked, answer, analysis FROM questions "
            "WHERE group_id = %s AND seq = %s LIMIT 1",
            (r["group_id"], r["sub_seq"]),
        )
        q = cursor.fetchone()
        if not q:
            continue
        cursor.execute(
            "SELECT label, content FROM options WHERE question_id = %s ORDER BY label",
            (q["id"],),
        )
        options = [{"label": o["label"], "content": o["content"]} for o in cursor.fetchall()]
        items[-1]["questions"].append({
            "no": r["seq"],
            "sub_seq": r["sub_seq"],
            "content": q["content"] or "",
            "marked": q["marked"] or "",
            "answer": q["answer"] or "",
            "analysis": q["analysis"] or "",
            "options": options,
        })

    return {
        "id": exam["id"],
        "level": exam["level"] or "",
        "total": exam["total"],
        "items": items,
    }


def _as_text(v) -> str:
    """防御性转字符串。"""
    if v is None:
        return ""
    return v if isinstance(v, str) else str(v)


# HTML 实体 → 字面字符。爬虫序列化时源站的 &gt; 等实体被原样保留，
# Markdown 里没有 HTML 解析，不还原就会显示成 "川村市&gt;レポーター募集"。
_ENTITIES = {
    "&lt;": "<", "&gt;": ">", "&quot;": '"', "&#39;": "'", "&nbsp;": " ",
    "&amp;": "&",  # 必须最后替换，否则 &amp;gt; 会被二次解码
}


def _unescape(s: str) -> str:
    for ent, ch in _ENTITIES.items():
        if ent != "&amp;":
            s = s.replace(ent, ch)
    return s.replace("&amp;", "&")


def _table_to_markdown(html: str) -> str:
    """把白名单 <table> 转成 Markdown 表格。

    article 里的表格是重建过的干净 HTML（仅 table/thead/tbody/tr/th/td/caption/br，
    见 docs/article-format.md），故用正则逐行拆解即可，无需引入解析器依赖。

    Markdown 表格不支持 rowspan/colspan——跨格单元格按「内容只落在起始格、其余留空」
    处理。信息检索题的表格多为规整网格，少数跨格处会略失结构，但内容不丢，打印可读。
    """
    # 源表未必有 <thead>（源站结构不规范，见 docs/article-format.md）。
    # 有 thead 时其行数即表头行数；没有则表头为空——不能拿首行数据当表头，
    # 否则那一行数据会被 Markdown 当成列名，内容看似还在却错位一行。
    head_html = ""
    m_head = re.search(r"<thead\b[^>]*>([\s\S]*?)</thead>", html, re.I)
    if m_head:
        head_html = m_head.group(1)
    head_row_count = len(re.findall(r"<tr\b", head_html, re.I)) if head_html else 0

    rows: list[list[str]] = []
    for tr in re.findall(r"<tr\b[^>]*>([\s\S]*?)</tr>", html, re.I):
        cells = []
        for m in re.finditer(r"<(t[dh])\b([^>]*)>([\s\S]*?)</\1>", tr, re.I):
            attrs, inner = m.group(2), m.group(3)
            # 格内换行 <br> → 空格：Markdown 表格单元格不能含真实换行
            inner = re.sub(r"<br\s*/?>", " ", inner, flags=re.I)
            inner = re.sub(r"<[^>]+>", "", inner)          # 剥掉残余标签
            inner = _unescape(inner)
            inner = inner.replace("|", "\\|")               # 转义列分隔符
            inner = re.sub(r"\s+", " ", inner).strip()
            cells.append(inner)
            # colspan 用空格占位，保持列对齐
            cs = re.search(r'colspan\s*=\s*["\']?(\d+)', attrs, re.I)
            if cs:
                cells.extend([""] * (int(cs.group(1)) - 1))
        if cells:
            rows.append(cells)

    if not rows:
        # 退化：连一行都没解析出来，剥成纯文本也好过输出裸 HTML
        return _unescape(re.sub(r"<[^>]+>", " ", html)).strip()

    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]

    caption = ""
    cap = re.search(r"<caption\b[^>]*>([\s\S]*?)</caption>", html, re.I)
    if cap:
        caption = _unescape(re.sub(r"<[^>]+>", "", cap.group(1))).strip()

    out = []
    if caption:
        out.append(f"*{caption}*")
        out.append("")

    # Markdown 表格语法强制要求一行表头 + 一行分隔线。
    if head_row_count:
        # 有 thead：首行当表头，其余（含 thead 里多余的行）作数据行
        header, body = rows[0], rows[1:]
    else:
        # 无 thead：用空表头占位，全部行都留作数据——不能挪用首行数据当列名
        header, body = [""] * width, rows

    out.append("| " + " | ".join(header) + " |")
    out.append("| " + " | ".join(["---"] * width) + " |")
    for r in body:
        out.append("| " + " | ".join(r) + " |")
    return "\n".join(out)


def _render_article(article) -> str:
    """把 article 的语义标记翻译成 Markdown。

    article 存的是带标记的半成品（规范见 docs/article-format.md），前端由
    `renderArticle()` 翻成 HTML。导出走 Markdown，需要一套等价映射，否则
    【U】【BOX】<table> 等标记会原样漏进文件里：

        【U】…【/U】      → <u>…</u>（Markdown 支持内联 HTML，打印有下划线）
        【BOX】…【/BOX】  → > 引用块（视觉上等价于边框信息块）
        【文章A】/【文章B】 → **文章A** 小标题
        <table>…</table> → Markdown 表格
        HTML 实体         → 字面字符
    """
    s = _as_text(article)
    if not s:
        return ""

    # 先把表格换成哨兵，避免后续的实体还原/标记替换动到表格内部
    tables: list[str] = []

    def _stash(m):
        tables.append(_table_to_markdown(m.group(0)))
        return f"\x00TBL{len(tables) - 1}\x00"

    s = re.sub(r"<table[\s\S]*?</table>", _stash, s, flags=re.I)

    s = _unescape(s)

    # 下划线：Markdown 无原生语法，用内联 <u>（GitHub/Typora/浏览器打印都认）
    s = re.sub(r"【U】([\s\S]*?)【/U】", r"<u>\1</u>", s)
    s = re.sub(r"【文章([AB])】", r"**文章\1**\n", s)

    # 【BOX】块 → 引用块：每行加 "> " 前缀。
    # 块内可能含表格哨兵——Markdown 的表格无法嵌在引用块里渲染，故把表格提到
    # 引用块之后单独成块（内容不丢，视觉上表格紧跟在信息框下方）。
    def _box(m):
        inner = m.group(1).strip("\n")
        pulled: list[str] = []

        def _pull(mm):
            pulled.append(mm.group(0))
            return ""

        inner = re.sub(r"\x00TBL\d+\x00", _pull, inner)
        lines = [ln for ln in inner.split("\n")]
        quoted = "\n".join(f"> {ln}" if ln.strip() else ">" for ln in lines)
        if pulled:
            quoted = quoted.rstrip("\n>") .rstrip() + "\n\n" + "\n\n".join(pulled)
        return quoted

    s = re.sub(r"【BOX】\n?([\s\S]*?)\n?【/BOX】", _box, s)

    # 残留的未配对标记（数据异常时）直接去掉，不让它漏给用户
    s = re.sub(r"【/?(?:U|BOX|文章[AB])】", "", s)

    # 还原表格；表格前后留空行，否则 Markdown 不把它当表格渲染
    s = re.sub(r"\x00TBL(\d+)\x00", lambda m: f"\n{tables[int(m.group(1))]}\n", s)
    return s.strip()


def _card_heading(card: dict) -> str:
    """卡片标题：单子题「第 N 题」，多子题「第 X–Y 题」，附题型名。"""
    qs = card["questions"]
    if len(qs) > 1:
        head = f"**第 {qs[0]['no']}–{qs[-1]['no']} 题**"
    else:
        head = f"**第 {qs[0]['no']} 题**"
    cat = category_name(card["category"])
    if cat:
        head += f"　（{cat}）"
    return head


# 导出模式。answers_only 供「只要一份答案」的场景（对答案、教师批改），
# 此前只有前两种，模型想满足「一份只有答案」只能退而给出两份含答案的卷。
MODE_QUESTIONS = "questions"
MODE_WITH_ANSWERS = "with_answers"
MODE_ANSWERS_ONLY = "answers_only"
VALID_MODES = (MODE_QUESTIONS, MODE_WITH_ANSWERS, MODE_ANSWERS_ONLY)

_MODE_TITLE = {
    MODE_QUESTIONS: "练习试卷",
    MODE_WITH_ANSWERS: "练习试卷（含答案）",
    MODE_ANSWERS_ONLY: "答案与解析",
}
_MODE_SUFFIX = {
    MODE_QUESTIONS: "",
    MODE_WITH_ANSWERS: "_答案",
    MODE_ANSWERS_ONLY: "_仅答案",
}


def render_exam_markdown(
    cursor, exam_id: int, with_answers: bool = False, mode: str | None = None,
) -> tuple[str, str] | None:
    """渲染试卷为 Markdown。返回 (文件名, 内容)；试卷不存在返回 None。

    mode:
    - questions      仅题目卷
    - with_answers   题目卷 + 末尾「答案与解析」一节
    - answers_only   只有答案与解析，不含题目（对答案、批改用）

    with_answers 为兼容旧调用保留：未显式传 mode 时，True→with_answers、False→questions。
    完形题按「文章 + 逐空选项」渲染；单选题按「题干 + 选项」渲染。
    """
    if mode is None:
        mode = MODE_WITH_ANSWERS if with_answers else MODE_QUESTIONS
    if mode not in VALID_MODES:
        raise ValueError(f"未知导出模式：{mode}")

    data = _fetch_export_data(cursor, exam_id)
    if data is None:
        return None

    level = data["level"] or "综合"
    lines: list[str] = []

    # 抬头
    lines.append(f"# JLPT {level} {_MODE_TITLE[mode]}")
    lines.append("")
    lines.append(f"- 试卷编号：#{data['id']}")
    lines.append(f"- 题目数量：{data['total']} 题")
    if mode != MODE_ANSWERS_ONLY:
        # 仅答案的那份不是用来作答的，不需要姓名/得分栏
        lines.append("- 姓名：____________　　得分：__________")
    lines.append("")
    lines.append("---")
    lines.append("")

    # 题目卷（仅答案模式跳过）
    for card in data["items"] if mode != MODE_ANSWERS_ONLY else []:
        qs = card["questions"]
        if not qs:
            continue
        lines.append(_card_heading(card))
        lines.append("")
        if card["article"]:
            # 有文章：先渲染文章（标记翻成 Markdown），再逐子题
            lines.append(_render_article(card["article"]))
            lines.append("")
            for q in qs:
                # 完形填空的子题无题干（空号在文章里），只列选项；
                # 阅读题的子题 content 是问句，必须输出，否则打印出来看不懂在问什么。
                stem = _render_article(q["content"])
                if stem:
                    lines.append(f"**{q['no']}.** {stem}")
                else:
                    lines.append(f"**（{q['sub_seq']}）**")
                lines.append("")
                for o in q["options"]:
                    lines.append(f"- {o['label'].upper()}. {_render_article(o['content'])}")
                lines.append("")
        else:
            # 无文章：逐子题输出题干 + 选项；划线词用下划线突出（纯占位括号跳过）。
            # 单选题只有一个子题，但这里不假设——按 qs 遍历，避免多子题题组
            # 因取 qs[0] 而静默丢掉后续子题。
            for q in qs:
                content = _render_article(q["content"])
                marked = _as_text(q["marked"])
                marked_core = re.sub(r"[（）()\[\]\s　]", "", marked)
                if marked and marked_core and marked in content:
                    content = content.replace(marked, f"<u>{marked}</u>")
                if len(qs) > 1:
                    lines.append(f"**（{q['no']}）**")
                lines.append(content)
                lines.append("")
                for o in q["options"]:
                    lines.append(f"- {o['label'].upper()}. {_render_article(o['content'])}")
                lines.append("")

    # 答案与解析
    if mode in (MODE_WITH_ANSWERS, MODE_ANSWERS_ONLY):
        if mode == MODE_WITH_ANSWERS:
            # 跟在题目卷之后，需要分隔线与小节标题；仅答案模式抬头已是「答案与解析」
            lines.append("---")
            lines.append("")
            lines.append("## 答案与解析")
            lines.append("")
        for card in data["items"]:
            for q in card["questions"]:
                ans = _as_text(q["answer"]).upper()
                lines.append(f"**第 {q['no']} 题**　正确答案：**{ans}**")
                analysis = _render_article(q["analysis"])
                if analysis:
                    lines.append("")
                    # 解析可能多行；逐行加引用前缀，否则第二行起会脱出引用块
                    for ln in analysis.split("\n"):
                        lines.append(f"> {ln}" if ln.strip() else ">")
                lines.append("")

    # 文件名带模式后缀，否则同一张卷导出的两份会同名、下载时互相覆盖
    filename = f"JLPT_{level}_exam_{data['id']}{_MODE_SUFFIX[mode]}.md"
    return filename, "\n".join(lines)
