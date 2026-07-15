import requests
import json
import re
import time
import os

from crawler.config import require, DEEPSEEK_API_URL, DEEPSEEK_MODEL

API_KEY = require("DEEPSEEK_API_KEY")
API_URL = DEEPSEEK_API_URL

MODEL = DEEPSEEK_MODEL

# ========== 题型配置 ==========
# fields: 原始数据字段名 -> 构建 prompt 时使用，用来统一提取题目和选项
#   - text: 题目字段名
#   - under_word: 划线词汇字段名（可选）
#   - choice: 选项列表字段名（列表形式，如 type_1）
#   - choice_keys: 选项字段名列表（分开形式，如 type_2 的 choice1-choice4）
#   - answer: 答案字段名
#   - analysis: 解析字段名
#   - date: 日期字段名

QUESTION_TYPES = {
    "type_1": {
        "fields": {
            "text": "text",
            "under_word": "under_word",
            "choice": "choice",
            "answer": "answer",
            "analysis": "analysis",
            "date": "date",
        },
        "prompt_extra": "",
    },
    "type_2": {
        "fields": {
            "text": "text",
            "choice_keys": ["choice1", "choice2", "choice3", "choice4"],
            "answer": "answer",
            "analysis": "analysis",
            "date": "date",
        },
        "prompt_extra": (
            "13. 本题为括号填空题，marked 字段必须为空字符串 \"\"，"
            "绝不要把题干里的括号「（　）」或空格填入 marked。"
        ),
    },
    "type_3": {
        # 句子语法1（文法形式判断）：题干带括号空，四个选项为扁平列表，无划线词。
        "fields": {
            "text": "text",
            "choice": "choice",
            "answer": "answer",
            "analysis": "analysis",
            "date": "date",
        },
        "prompt_extra": (
            "13. 本题为括号填空选语法题，marked 字段必须为空字符串 \"\"，"
            "绝不要把题干里的括号「（　）」或空格填入 marked。"
            "14. 解析请侧重语法形式与接续规则，说明为何该语法形式最契合括号处语境。"
        ),
    },
    "type_4": {
        # 句子语法2（文の組み立て / 排序题）：题干含 4 个空位标记（＿＿ 与 ＿★＿），
        # 四个选项是待排序的句子碎片，answer = ★ 处应填的选项号。
        "fields": {
            "text": "text",
            "choice": "choice",
            "answer": "answer",
            "analysis": "analysis",
            "date": "date",
        },
        "prompt_extra": (
            "13. 本题为排序题（文の組み立て），marked 字段必须为空字符串 \"\"。"
            "14. content 中的空位标记「＿＿」与「＿★＿」必须原样保留，不得删除或改写，"
            "也不要把碎片填进空位——题干保持带空位的形式。"
            "15. 四个选项是待排序的句子碎片，务必原样保留、顺序不变，"
            "绝不可改写、合并或重新排列；输出 options 的 a/b/c/d 必须与输入顺序完全一致。"
            "16. answer 表示 ★ 处应填入的选项号，请沿用原始答案，不要自行重新推导或更改。"
            "17. analysis 请给出四个碎片的完整正确排列顺序（如 4→2→3→1），"
            "说明整句还原后的意思，并指出 ★ 处为何是该选项。"
        ),
    },
}


def _extract_options(question_data, config):
    """从原始数据中提取选项，统一返回 {"a": ..., "b": ..., "c": ..., "d": ...} 字典"""
    fields = config["fields"]
    option_labels = ["a", "b", "c", "d"]

    if "choice_keys" in fields:
        keys = fields["choice_keys"]
        return {label: question_data.get(keys[i], "") for i, label in enumerate(option_labels)}
    elif "choice" in fields:
        raw = question_data.get(fields["choice"], [])
        return {label: (raw[i] if i < len(raw) else "") for i, label in enumerate(option_labels)}
    return {label: "" for label in option_labels}


def _build_question_context(question_data, config):
    """将原始数据转为统一格式供 prompt 使用"""
    fields = config["fields"]
    options = _extract_options(question_data, config)
    ctx = {
        "content": question_data.get(fields["text"], ""),
        "options": options,
        "answer": question_data.get(fields["answer"], ""),
        "date": question_data.get(fields["date"], ""),
        "analysis": question_data.get(fields["analysis"], ""),
    }
    if "under_word" in fields:
        ctx["under_word"] = question_data.get(fields["under_word"], "")
    return ctx


def call_deepseek(prompt, retries=3, timeout=60):
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }

    data = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": "你是一个严谨的日语考试校对专家"},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.2
    }

    last_err = None
    for attempt in range(1, retries + 1):
        try:
            response = requests.post(API_URL, headers=headers, json=data, timeout=timeout)
            response.raise_for_status()
            result = response.json()
            return result["choices"][0]["message"]["content"]
        except (requests.RequestException, ValueError, KeyError, IndexError) as e:
            # 网络错误 / 非 JSON 响应 / 返回结构异常（如限流错误体没有 choices）都在此兜住
            last_err = e
            print(f"  DeepSeek 调用失败（第 {attempt}/{retries} 次）: {e}")
            if attempt < retries:
                time.sleep(2 * attempt)  # 线性退避：2s、4s...

    raise RuntimeError(f"DeepSeek 调用重试 {retries} 次仍失败: {last_err}")


def build_prompt(question_data, question_type="type_1"):
    config = QUESTION_TYPES.get(question_type)
    if config is None:
        raise ValueError(f"未知的题型: {question_type}，支持的类型: {list(QUESTION_TYPES.keys())}")

    ctx = _build_question_context(question_data, config)
    extra = config.get("prompt_extra", "")

    return f"""
你是日语能力考试(JLPT)专家 + 语言校对专家，请对题目进行严格校验与修正。

要求：
1. 校验题目和选项中是否存在错误，如果存在错误修改错误
2. 在解析中给出正确答案原因
3. 在解析中指出涉及语法点
4. 在解析中用中文解释，简洁清晰
5. 输出为json格式
6. 分析每个选项为什么对/错，注意将每个选项拆开不要将三个错误选项合并在一起解释
7. 如果题目为考察读音的题，尽量指出选项中的词都对应什么汉字，以及其中文意思
8. 为题目区分难度（1-9分）
9. 统一标点符号格式
10. 删除无用的换行符以及其他制表符
11. 答案存在对应关系，原数据中的1对应a，2对应b，3对应c，4对应d
12. 务必在解析中使用相同的格式输出内容，保证我输出的数据统一且美观。analysis 字段的文本必须严格按照以下结构排版，不可擅自改变：
   【答案解析】...
   【错项分析】a选项:...， b选项错:...
{extra}

输出必须为JSON：

{{
  "content": "...",
  "marked":"",
  "options": {{
    "a": "...",
    "b": "...",
    "c": "...",
    "d": "..."
  }},
  "level": "N1",
  "answer": "1",
  "date": "2023-07",
  "answer_changed": true,
  "analysis": "【答案解析】...\\n【错项分析】...",
  "difficulty": "...",
  "knowledge_points":["原因表达", "...."],
  "error_flags": []
}}

---
【参考示例】
输入示例：(假装这里有个题)
输出示例：
{{
  "content": "明日雨が降ったらハイキングに行きません。",
  "marked": "降ったら",
  "options": {{"a": "降るなら", "b": "降れば", "c": "降ったら", "d": "降っても"}},
  "level": "N1",
  "answer": "c",
  "date": "2023-07",
  "answer_changed": false,
  "analysis": "【答案解析】正确答案是c。表示假定条件，后接个人意志时，通常使用「たら」。\\n【错项分析】a选项「なら」接在名词后；b选项「ば」后半句不能接意志表达；d选项「ても」表示逆接。",
  "difficulty": "3",
  "knowledge_points":["条件表达", "たら的用法"],
  "error_flags": []
}}
---

原始数据：
{json.dumps(ctx, ensure_ascii=False)}
"""


def safe_parse(content):
    try:
        return json.loads(content)
    except:
        start = content.find("{")
        end = content.rfind("}")
        return json.loads(content[start:end+1])


# 原始数据答案是数字 1-4，对应选项 a-d。模型偶尔不按提示做映射、直接回数字，
# 故在代码里做确定性归一化，不依赖模型可靠性。
_NUM_TO_LETTER = {"1": "a", "2": "b", "3": "c", "4": "d"}


def normalize_answer(ans):
    """把答案统一成 a/b/c/d：数字按位置映射，字母原样保留（去空格、转小写）。"""
    s = str(ans).strip().lower()
    return _NUM_TO_LETTER.get(s, s)


def validate_result(res):
    assert res["answer"] in ["a", "b", "c", "d"]
    assert len(res["options"]) == 4
    assert res["analysis"] != ""


def process_one(question_data, question_type="type_1"):
    prompt = build_prompt(question_data, question_type)

    raw = call_deepseek(prompt)

    parsed = safe_parse(raw)

    parsed["answer"] = normalize_answer(parsed.get("answer", ""))

    validate_result(parsed)

    return parsed


# ========== 文章语法（text_grammar / 文章完形）校验 ==========
# 结构为「一篇文章 + N 道填空小题」，与扁平单题不同：整篇一次送审、带全文上下文，
# 但答案与选项一律沿用抓取原值（不让模型重解，避免多空答案错位），
# 模型只负责逐空补写标准格式解析、难度、知识点，以及整篇级别。

_LETTERS = ["a", "b", "c", "d"]


def build_passage_prompt(passage):
    # 组织每道小题：题号 + 4 个选项（带 a-d 标签）+ 已知正确答案（字母）
    lines = []
    for sub in passage["questions"]:
        opts = sub["options"]
        labeled = "，".join(f"{_LETTERS[i]}. {opts[i]}" for i in range(len(opts)))
        ans = normalize_answer(sub["answer"])
        lines.append(f"空（{sub['no']}）选项：{labeled}；正确答案：{ans}")
    blanks_block = "\n".join(lines)
    ref = passage.get("analysis", "")

    return f"""
你是日语能力考试(JLPT)专家 + 语言校对专家。下面是一道「文章语法」（文章の文法）大题：
一篇文章中有多个用 （数字） 标出的空，每个空是一道四选一小题。请为每个空撰写严谨的中文解析。

严格要求：
1. 答案与选项均为权威原值，绝对不要改动、不要重新排序、不要重新推导答案。
2. 不要修改文章原文。
3. 为每个空输出：analysis（中文解析）、difficulty（1-9 难度）、knowledge_points（语法/词汇点数组）。
4. analysis 必须严格采用以下结构排版：
   【答案解析】...（结合上下文说明为何该选项正确）
   【错项分析】a选项:...，b选项:...，c选项:...，d选项:...（逐项，不可合并）
5. 可参考下方“原始解析”理解出题意图，但需重写为上述统一格式与措辞。
6. 输出必须为 JSON，questions 数组顺序与题号一致。

输出 JSON 格式：
{{
  "level": "N1",
  "questions": [
    {{"no": 1, "answer": "c", "difficulty": "5", "knowledge_points": ["..."], "analysis": "【答案解析】...\\n【错项分析】a选项:...，b选项:...，c选项:...，d选项:..."}}
  ]
}}

文章：
{passage["article"]}

各空选项与答案：
{blanks_block}

原始解析（供参考，请重写为统一格式）：
{ref}
"""


def process_passage(passage):
    """校验一篇文章完形题。返回嵌套结构：article + 逐空 options/answer/analysis/难度/知识点。

    答案、选项取抓取原值；解析、难度、知识点取模型输出；级别优先从 date 提取。
    """
    raw = call_deepseek(build_passage_prompt(passage))
    parsed = safe_parse(raw)
    llm_by_no = {int(q.get("no")): q for q in parsed.get("questions", []) if q.get("no") is not None}

    # 级别：优先从 date（如 "2011-07-N1"）提取，回退模型输出，再回退 N1
    m = re.search(r"N[1-5]", passage.get("date", "") or "")
    level = m.group(0) if m else (parsed.get("level") or "N1")

    out_questions = []
    for sub in passage["questions"]:
        no = int(sub["no"])
        opts = sub["options"]
        options = {_LETTERS[i]: (opts[i] if i < len(opts) else "") for i in range(4)}
        answer = normalize_answer(sub["answer"])
        lq = llm_by_no.get(no, {})
        analysis = (lq.get("analysis") or "").strip()

        # 逐空质量校验：答案合法、四选项齐、解析非空
        assert answer in _LETTERS, f"空{no} 答案非法: {answer}"
        assert all(options[l] for l in _LETTERS), f"空{no} 选项不全"
        assert analysis, f"空{no} 解析为空"

        out_questions.append({
            "no": no,
            "options": options,
            "answer": answer,
            "analysis": analysis,
            "difficulty": str(lq.get("difficulty", "")).strip(),
            "knowledge_points": lq.get("knowledge_points", []) or [],
        })

    return {
        "id": passage.get("id"),
        "date": passage.get("date", ""),
        "level": level,
        "article": passage["article"],
        "questions": out_questions,
    }


# ========== 阅读理解（reading_short / 短篇内容理解）校验 ==========
# 结构为「一段短文 + 一个问句 + 4 整句选项」。答案与选项沿用抓取原值，
# 模型只补解析、难度、知识点，级别优先从 date 提取。

def build_reading_prompt(item):
    opts = item["choice"]
    labeled = "\n".join(f"{_LETTERS[i]}. {opts[i]}" for i in range(len(opts)))
    ans = normalize_answer(item["answer"])
    return f"""
你是日语能力考试(JLPT)专家 + 语言校对专家。下面是一道「阅读理解」（内容理解·短篇）题：
一段短文 + 一个问句 + 四个选项。请撰写严谨的中文解析。

严格要求：
1. 答案与选项均为权威原值，绝对不要改动、不要重新排序、不要重新推导答案。
2. 不要修改文章原文与问句。
3. analysis 必须严格采用以下结构排版：
   【答案解析】...（结合原文说明为何该选项正确，可引用原文关键句）
   【错项分析】a选项:...，b选项:...，c选项:...，d选项:...（逐项，不可合并）
4. 输出为 JSON：analysis（中文解析）、difficulty（1-9 难度）、knowledge_points（考点/技巧数组，如“主旨理解”“指示词指代”“筆者の主張”）。

输出 JSON 格式：
{{
  "answer": "{ans}",
  "difficulty": "5",
  "knowledge_points": ["主旨理解", "..."],
  "analysis": "【答案解析】...\\n【错项分析】a选项:...，b选项:...，c选项:...，d选项:..."
}}

文章：
{item["article"]}

问句：{item["question"]}

选项：
{labeled}

正确答案：{ans}
"""


def process_reading(item):
    """校验一道阅读理解题。答案/选项/文章/问句取抓取原值；解析、难度、知识点取模型输出。"""
    raw = call_deepseek(build_reading_prompt(item))
    parsed = safe_parse(raw)

    opts = item["choice"]
    options = {_LETTERS[i]: (opts[i] if i < len(opts) else "") for i in range(4)}
    answer = normalize_answer(item["answer"])
    analysis = (parsed.get("analysis") or "").strip()

    assert answer in _LETTERS, f"答案非法: {answer}"
    assert all(options[l] for l in _LETTERS), "选项不全"
    assert analysis, "解析为空"

    m = re.search(r"N[1-5]", item.get("date", "") or "")
    level = m.group(0) if m else "N1"

    return {
        "id": item.get("id"),
        "date": item.get("date", ""),
        "level": level,
        "article": item["article"],
        "question": item["question"],
        "options": options,
        "answer": answer,
        "analysis": analysis,
        "difficulty": str(parsed.get("difficulty", "")).strip(),
        "knowledge_points": parsed.get("knowledge_points", []) or [],
    }


# ========== 中长篇阅读（一篇多问）校验 ==========
# 结构为「一篇文章 + N 个问句」，整篇一次送审、带全文上下文；答案与选项沿用抓取原值，
# 模型逐问补解析、难度、知识点。文章中的 【U】…【/U】 为下划线标记，请勿改动。

def build_reading_passage_prompt(passage):
    lines = []
    for sub in passage["questions"]:
        opts = sub["choice"]
        labeled = "，".join(f"{_LETTERS[i]}. {opts[i]}" for i in range(len(opts)))
        ans = normalize_answer(sub["answer"])
        lines.append(f"问{sub['no']}：{sub['question']}\n  选项：{labeled}\n  正确答案：{ans}")
    q_block = "\n".join(lines)

    return f"""
你是日语能力考试(JLPT)专家 + 语言校对专家。下面是一道「阅读理解」大题：
一篇文章 + 多个问句，每个问句是一道四选一小题。请为每个问句撰写严谨的中文解析。

严格要求：
1. 答案与选项均为权威原值，绝对不要改动、不要重新排序、不要重新推导答案。
2. 不要修改文章原文。文章中的「【U】…【/U】」是原文下划线标记，问句可能引用，请理解但不要改写。
3. 为每个问句输出：analysis（中文解析）、difficulty（1-9 难度）、knowledge_points（考点/技巧数组）。
4. analysis 必须严格采用以下结构排版：
   【答案解析】...（结合原文说明为何该选项正确，可引用原文关键句）
   【错项分析】a选项:...，b选项:...，c选项:...，d选项:...（逐项，不可合并）
5. 输出必须为 JSON，questions 数组顺序与问号一致。

输出 JSON 格式：
{{
  "level": "N1",
  "questions": [
    {{"no": 1, "answer": "c", "difficulty": "5", "knowledge_points": ["主旨理解"], "analysis": "【答案解析】...\\n【错项分析】a选项:...，b选项:...，c选项:...，d选项:..."}}
  ]
}}

文章：
{passage["article"]}

问句与选项：
{q_block}
"""


def process_reading_passage(passage):
    """校验一篇多问阅读题。答案/选项/文章/问句取抓取原值；解析、难度、知识点取模型输出。"""
    raw = call_deepseek(build_reading_passage_prompt(passage))
    parsed = safe_parse(raw)
    llm_by_no = {int(q.get("no")): q for q in parsed.get("questions", []) if q.get("no") is not None}

    m = re.search(r"N[1-5]", passage.get("date", "") or "")
    level = m.group(0) if m else (parsed.get("level") or "N1")

    out_questions = []
    for sub in passage["questions"]:
        no = int(sub["no"])
        opts = sub["choice"]
        options = {_LETTERS[i]: (opts[i] if i < len(opts) else "") for i in range(4)}
        answer = normalize_answer(sub["answer"])
        lq = llm_by_no.get(no, {})
        analysis = (lq.get("analysis") or "").strip()

        assert answer in _LETTERS, f"问{no} 答案非法: {answer}"
        assert all(options[l] for l in _LETTERS), f"问{no} 选项不全"
        assert analysis, f"问{no} 解析为空"

        out_questions.append({
            "no": no,
            "question": sub["question"],
            "options": options,
            "answer": answer,
            "analysis": analysis,
            "difficulty": str(lq.get("difficulty", "")).strip(),
            "knowledge_points": lq.get("knowledge_points", []) or [],
        })

    return {
        "id": passage.get("id"),
        "date": passage.get("date", ""),
        "level": level,
        "article": passage["article"],
        "questions": out_questions,
    }


if __name__ == "__main__":
    import argparse
    import os

    parser = argparse.ArgumentParser(description="JLPT题目校验")
    parser.add_argument("--type", dest="question_type", default="type_1",
                        choices=list(QUESTION_TYPES.keys()),
                        help="题目类型")
    parser.add_argument("--input", required=True, help="输入JSON文件路径")
    parser.add_argument("--output", required=True, help="输出JSON文件路径")
    parser.add_argument("--fresh", action="store_true",
                        help="忽略已有输出，全部重新校验（默认断点续跑：跳过输出中已成功的题）")
    parser.add_argument("--passage", action="store_true",
                        help="文章语法（text_grammar）模式：输入为嵌套的文章完形题，逐篇校验")
    parser.add_argument("--reading", action="store_true",
                        help="阅读理解（reading_short）模式：一段短文 + 一问，逐题校验")
    parser.add_argument("--reading-passage", dest="reading_passage", action="store_true",
                        help="中长篇阅读模式：一篇文章 + 多问的嵌套结构，逐篇校验")
    args = parser.parse_args()

    unit = "篇" if (args.passage or args.reading_passage) else "题"

    with open(args.input, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 断点续跑：若输出已存在，载入已成功的题，本次只补齐缺失/失败的题，避免重复消耗 API。
    validated_by_id = {}
    if not args.fresh and os.path.exists(args.output):
        with open(args.output, "r", encoding="utf-8") as f:
            for q in json.load(f):
                validated_by_id[q.get("id")] = q
        print(f"检测到已有输出，{len(validated_by_id)} {unit}已完成，仅补齐剩余")

    todo = [item for item in data if item.get("id") not in validated_by_id]
    print(f"待处理 {len(todo)} {unit}（共 {len(data)} {unit}）")

    def _save():
        merged = sorted(validated_by_id.values(), key=lambda q: (q.get("id") is None, q.get("id")))
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(merged, f, ensure_ascii=False, indent=2)

    success = 0
    failed = []
    for i, item in enumerate(todo, 1):
        qid = item.get("id")
        print(f"[{i}/{len(todo)}] 正在处理 ID: {qid}")
        try:
            if args.passage:
                result = process_passage(item)
            elif args.reading_passage:
                result = process_reading_passage(item)
            elif args.reading:
                result = process_reading(item)
            else:
                result = process_one(item, question_type=args.question_type)
            result["id"] = qid
            validated_by_id[qid] = result
            success += 1
            print(f"处理成功 ID: {qid}")
        except Exception as e:
            failed.append(qid)
            print(f"处理失败 ID: {qid}, 错误: {repr(e)}")

        # 每 10 题落盘一次，防止中途崩溃前功尽弃
        if i % 10 == 0:
            _save()
        print("-" * 50)
        time.sleep(1)

    _save()
    print(f"处理完成，已保存到 {args.output}")
    print(f"本轮成功 {success} {unit}，失败 {len(failed)} {unit}" + (f"，失败 ID: {failed}" if failed else ""))
    print(f"输出累计 {len(validated_by_id)} {unit}（可再次运行同一命令补齐失败项）")