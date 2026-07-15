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
    """富文本字段当前为纯文本；防御性转字符串。"""
    if v is None:
        return ""
    return v if isinstance(v, str) else str(v)


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


def render_exam_markdown(cursor, exam_id: int, with_answers: bool = False) -> tuple[str, str] | None:
    """渲染试卷为 Markdown。返回 (文件名, 内容)；试卷不存在返回 None。

    with_answers=False：仅题目卷。
    with_answers=True ：题目卷 + 末尾「答案与解析」一节，便于打印后自查。
    完形题按「文章 + 逐空选项」渲染；单选题按「题干 + 选项」渲染。
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
    for card in data["items"]:
        qs = card["questions"]
        if not qs:
            continue
        lines.append(_card_heading(card))
        lines.append("")
        if card["article"]:
            # 完形：先文章，再逐空选项
            lines.append(_as_text(card["article"]))
            lines.append("")
            for q in qs:
                lines.append(f"**（{q['sub_seq']}）**")
                for o in q["options"]:
                    lines.append(f"- {o['label'].upper()}. {_as_text(o['content'])}")
                lines.append("")
        else:
            # 单选：题干 + 选项；划线词用下划线突出（纯占位括号跳过）
            q = qs[0]
            content = _as_text(q["content"])
            marked = _as_text(q["marked"])
            marked_core = re.sub(r"[（）()\[\]\s　]", "", marked)
            if marked and marked_core and marked in content:
                content = content.replace(marked, f"<u>{marked}</u>")
            lines.append(content)
            lines.append("")
            for o in q["options"]:
                lines.append(f"- {o['label'].upper()}. {_as_text(o['content'])}")
            lines.append("")

    # 答案与解析
    if with_answers:
        lines.append("---")
        lines.append("")
        lines.append("## 答案与解析")
        lines.append("")
        for card in data["items"]:
            for q in card["questions"]:
                ans = _as_text(q["answer"]).upper()
                lines.append(f"**第 {q['no']} 题**　正确答案：**{ans}**")
                analysis = _as_text(q["analysis"])
                if analysis:
                    lines.append("")
                    lines.append(f"> {analysis}")
                lines.append("")

    filename = f"JLPT_{level}_exam_{data['id']}.md"
    return filename, "\n".join(lines)
