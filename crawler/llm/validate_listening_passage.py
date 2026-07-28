"""综合理解（一段音频 N 子题）审核：逐子题用脚本判答案 + 生成中文解析。

复用 validate.py 的 call_deepseek/safe_parse/normalize_answer。
输入嵌套结构 result_XX.json（{id,audio_url,article,questions:[{no,options,answer}]}），
输出同结构 + 每子题附 model_answer/answer_agrees/analysis/text_issues；断点续跑。

用法：python -m crawler.llm.validate_listening_passage --input data/raw/result_85.json --output data/raw/result_85_listened.json
"""
import argparse
import json
import os
import re
import time

from crawler.llm.validate import call_deepseek, safe_parse, normalize_answer, _LETTERS


def build_prompt(article, sub):
    opts = sub.get("options", {}) or {}
    labeled = "，".join(f"{l}. {opts[l]}" for l in _LETTERS if l in opts) or "（选项在音频里，无文字）"
    recorded = normalize_answer(sub.get("answer", ""))
    setsumon = (sub.get("question") or "").strip()
    q_line = f"本小题的设问是：{setsumon}\n" if setsumon else ""
    return f"""
你是日语能力考试(JLPT)「综合理解（統合理解）」听力题的资深审校专家。
下面是一段听力脚本 + 针对它的一个小题（本题是同一段音频的第 {sub.get('no')} 小题）。
{q_line}题目人工录入，**可能有错**。请独立严格审核。务必针对上面这个具体设问作答，不要与同段的其他小题混淆。

请完成三项：
1. 【独立作答】你自己通读脚本后独立选出该小题的正确答案（a/b/c/d）。若选项无文字（在音频里），
   依据脚本内容判断录入答案是否合理即可。先独立判断，再与录入答案比较。
2. 【文本问题】指出脚本或选项中的错别字、乱码、OCR 错误。
3. 【生成解析】写中文解析：说明该小题答案对应脚本中的哪句话，其余选项为何不对。

严格要求：不改写脚本/选项/录入答案，只判断与报告。「女：」「男：」是说话人标记。

输出必须为 JSON：
{{
  "model_answer": "c",
  "answer_agrees": true,
  "answer_confidence": "high",
  "text_issues": [],
  "analysis": "【答案解析】...\\n【错项分析】..."
}}

听力脚本：
{article}

第 {sub.get('no')} 小题选项：{labeled}
录入答案（待核对，勿盲信）：{recorded}
"""


def process_sub(article, sub):
    raw = call_deepseek(build_prompt(article, sub))
    parsed = safe_parse(raw)
    recorded = normalize_answer(sub.get("answer", ""))
    model_answer = normalize_answer(parsed.get("model_answer", "") or "")
    agrees = bool(model_answer) and model_answer == recorded
    out = dict(sub)
    out["answer"] = recorded
    out["model_answer"] = model_answer
    out["answer_agrees"] = agrees
    out["answer_confidence"] = str(parsed.get("answer_confidence", "")).strip()
    out["text_issues"] = parsed.get("text_issues", []) or []
    out["analysis"] = (parsed.get("analysis") or "").strip()
    return out


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--fresh", action="store_true")
    args = p.parse_args()

    with open(args.input, encoding="utf-8") as f:
        data = json.load(f)

    done = {}
    if not args.fresh and os.path.exists(args.output):
        with open(args.output, encoding="utf-8") as f:
            for r in json.load(f):
                done[r["id"]] = r

    out_by_id = dict(done)
    total = len(data)
    for i, item in enumerate(data, 1):
        qid = item["id"]
        if qid in done and all(q.get("analysis") for q in done[qid].get("questions", [])):
            continue
        print(f"[{i}/{total}] 组 ID {qid}")
        try:
            newq = [process_sub(item.get("article", ""), sub) for sub in item.get("questions", [])]
            rec = dict(item)
            rec["questions"] = newq
            out_by_id[qid] = rec
        except Exception as e:
            print(f"  失败 ID {qid}: {e!r}")
        if i % 5 == 0:
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump([out_by_id[k] for k in sorted(out_by_id)], f, ensure_ascii=False, indent=2)
        time.sleep(0.5)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump([out_by_id[k] for k in sorted(out_by_id)], f, ensure_ascii=False, indent=2)
    print(f"完成：{len(out_by_id)}/{total} 组")
