import requests
import json
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


def validate_result(res):
    assert res["answer"] in ["a", "b", "c", "d"]
    assert len(res["options"]) == 4
    assert res["analysis"] != ""


def process_one(question_data, question_type="type_1"):
    prompt = build_prompt(question_data, question_type)

    raw = call_deepseek(prompt)

    parsed = safe_parse(raw)

    validate_result(parsed)

    return parsed


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="JLPT题目校验")
    parser.add_argument("--type", dest="question_type", default="type_1",
                        choices=list(QUESTION_TYPES.keys()),
                        help="题目类型")
    parser.add_argument("--input", required=True, help="输入JSON文件路径")
    parser.add_argument("--output", required=True, help="输出JSON文件路径")
    args = parser.parse_args()

    with open(args.input, "r", encoding="utf-8") as f:
        data = json.load(f)

    validated_data = []

    for item in data:
        print(f"正在处理题目 ID: {item.get('id')}")
        try:
            result = process_one(item, question_type=args.question_type)
            result["id"] = item.get("id")
            validated_data.append(result)
            print(f"处理成功 ID: {item.get('id')}")
        except Exception as e:
            print(f"处理失败 ID: {item.get('id')}, 错误: {e}")

        print("-" * 50)
        time.sleep(1)

    print(f"处理完成，准备保存到 {args.output}")
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(validated_data, f, ensure_ascii=False, indent=2)
    print("保存成功！")