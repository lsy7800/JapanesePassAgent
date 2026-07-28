"""把听力题 --listening 审核产物应用为可入库的 _checked.json。

处理逻辑（对每套 result_XX + result_XX_listened）：
  1. 文本修正：从审核的 text_issues 自动抽取「A应为B」替换对（过滤误报），应用到
     question/article/choice。仅采纳明确的「A」应为「B」模式，语义模糊的跳过（保守）。
  2. 解析回填：用审核生成的中文 analysis。
  3. 答案分歧：answer_agrees=False 的题保留录入答案（不自动改），记入 need_review 清单。
  4. 产出 result_XX_checked.json + result_XX_review.json（存疑清单）。

用法：python -m crawler.llm.apply_listening_fixes 80 81 82
"""
import json
import os
import re
import sys

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "data", "raw")

# 误报关键词：审核自己说"不影响/可接受/口语"等，不改
IGNORE = re.compile(
    r"不影响|可接受|非严格|非关键|不构成|不判定|口语|不视为|但结合上下文|"
    r"略显|通常写作|可省略|非正式|不强制|无需修改|不算错误|可保留|并非错误"
)
# 「A」应为「B」及其变体
PAT = re.compile(
    r"[「'\"“『]([^」'\"”』]{1,40})[」'\"”』]\s*"
    r"(?:应为|应写作|疑为|应改为|正确的?应?为|通常应为|应是|之误)\s*"
    r"[「'\"“『]([^」'\"”』]{1,40})[」'\"”』]"
)


def extract_pair(issue):
    if IGNORE.search(issue):
        return None
    m = PAT.search(issue)
    if not m:
        return None
    a, b = m.group(1).strip(), m.group(2).strip()
    if not a or not b or a == b:
        return None
    return a, b


def apply_fixes(rec, pairs):
    """把替换对应用到 question/article/choice；返回实际命中的替换。"""
    applied = []
    for a, b in pairs:
        hit = False
        if a in (rec.get("question") or ""):
            rec["question"] = rec["question"].replace(a, b); hit = True
        if a in (rec.get("article") or ""):
            rec["article"] = rec["article"].replace(a, b); hit = True
        newch = []
        for c in rec.get("choice", []):
            if a in c:
                c = c.replace(a, b); hit = True
            newch.append(c)
        rec["choice"] = newch
        if hit:
            applied.append((a, b))
    return applied


def process(sb):
    raw_path = os.path.join(DATA, f"result_{sb}.json")
    val_path = os.path.join(DATA, f"result_{sb}_listened.json")
    raw = {r["id"]: r for r in json.load(open(raw_path, encoding="utf-8"))}
    val = {r["id"]: r for r in json.load(open(val_path, encoding="utf-8"))}

    review = []
    fix_count = 0
    for qid, rec in raw.items():
        v = val.get(qid, {})
        # 1) 文本修正
        pairs = []
        for iss in v.get("text_issues", []):
            p = extract_pair(iss)
            if p:
                pairs.append(p)
        if pairs:
            applied = apply_fixes(rec, pairs)
            fix_count += len(applied)
        # 2) 解析回填
        ana = (v.get("analysis") or "").strip()
        if ana:
            rec["analysis"] = ana
        # 3) 答案分歧 → 保留录入，记存疑
        if not v.get("answer_agrees", True) and v.get("model_answer"):
            review.append({
                "id": qid,
                "recorded": rec.get("answer"),
                "model": v.get("model_answer"),
                "confidence": v.get("answer_confidence"),
                "question_relevant": v.get("question_relevant"),
                "note": (v.get("relevance_note") or v.get("audit_comment") or "")[:120],
            })

    out = [raw[k] for k in sorted(raw)]
    json.dump(out, open(os.path.join(DATA, f"result_{sb}_checked.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    json.dump(review, open(os.path.join(DATA, f"result_{sb}_review.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"result_{sb}: {len(out)} 题, 文本修正 {fix_count} 处, 答案存疑 {len(review)} 题 -> "
          f"{[r['id'] for r in review]}")


if __name__ == "__main__":
    for sb in (sys.argv[1:] or ["80", "81", "82"]):
        process(sb)
