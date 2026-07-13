"""试卷 Markdown 导出：把已落库的试卷渲染为可下载/打印的 Markdown 文本。

数据来自 exams / exam_items / question_groups / questions / options 五表，
不调用 LLM。生成结构：抬头 → 题目卷（不含答案）→ （可选）答案与解析另起一节。
"""
from backend.config.categories import category_name


def _fetch_export_data(cursor, exam_id: int) -> dict | None:
    """取试卷抬头 + 各题（题干/划线词/选项/答案/解析/题型）。不存在返回 None。"""
    cursor.execute(
        "SELECT id, level, total, status FROM exams WHERE id = %s",
        (exam_id,),
    )
    exam = cursor.fetchone()
    if exam is None:
        return None

    cursor.execute(
        "SELECT seq, group_id FROM exam_items WHERE exam_id = %s ORDER BY seq",
        (exam_id,),
    )
    item_rows = cursor.fetchall()

    items = []
    for it in item_rows:
        cursor.execute(
            "SELECT category FROM question_groups WHERE id = %s",
            (it["group_id"],),
        )
        g = cursor.fetchone()
        cursor.execute(
            "SELECT id, content, marked, answer, analysis FROM questions "
            "WHERE group_id = %s ORDER BY seq LIMIT 1",
            (it["group_id"],),
        )
        q = cursor.fetchone()
        if not q:
            continue
        cursor.execute(
            "SELECT label, content FROM options WHERE question_id = %s ORDER BY label",
            (q["id"],),
        )
        options = [{"label": o["label"], "content": o["content"]} for o in cursor.fetchall()]
        items.append({
            "seq": it["seq"],
            "category": g["category"] if g else None,
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
    """富文本字段当前为纯文本；防御性转字符串。"""
    if v is None:
        return ""
    return v if isinstance(v, str) else str(v)


def render_exam_markdown(cursor, exam_id: int, with_answers: bool = False) -> tuple[str, str] | None:
    """渲染试卷为 Markdown。返回 (文件名, 内容)；试卷不存在返回 None。

    with_answers=False：仅题目卷。
    with_answers=True ：题目卷 + 末尾「答案与解析」一节，便于打印后自查。
    """
    data = _fetch_export_data(cursor, exam_id)
    if data is None:
        return None

    level = data["level"] or "综合"
    lines: list[str] = []

    # 抬头
    lines.append(f"# JLPT {level} 练习试卷")
    lines.append("")
    lines.append(f"- 试卷编号：#{data['id']}")
    lines.append(f"- 题目数量：{data['total']} 题")
    lines.append("- 姓名：____________　　得分：__________")
    lines.append("")
    lines.append("---")
    lines.append("")

    # 题目卷
    for it in data["items"]:
        cat = category_name(it["category"])
        head = f"**第 {it['seq']} 题**"
        if cat:
            head += f"　（{cat}）"
        lines.append(head)
        lines.append("")
        content = _as_text(it["content"])
        # 划线词用 Markdown 下划线（**加粗+下划线**），突出考点
        marked = _as_text(it["marked"])
        if marked and marked in content:
            content = content.replace(marked, f"<u>{marked}</u>")
        lines.append(content)
        lines.append("")
        for o in it["options"]:
            lines.append(f"- {o['label'].upper()}. {_as_text(o['content'])}")
        lines.append("")

    # 答案与解析
    if with_answers:
        lines.append("---")
        lines.append("")
        lines.append("## 答案与解析")
        lines.append("")
        for it in data["items"]:
            ans = _as_text(it["answer"]).upper()
            lines.append(f"**第 {it['seq']} 题**　正确答案：**{ans}**")
            analysis = _as_text(it["analysis"])
            if analysis:
                lines.append("")
                lines.append(f"> {analysis}")
            lines.append("")

    filename = f"JLPT_{level}_exam_{data['id']}.md"
    return filename, "\n".join(lines)
