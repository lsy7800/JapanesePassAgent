"""AI 组卷规划器：把用户自然语言需求 + 薄弱点 → 结构化组卷方案。

设计：一次 LLM 调用产出方案，再由 exam_builder 确定性建卷。
LLM 只负责"决定策略/配额"，不直接操作数据库，保证 exam_id 可靠。
任何解析/校验失败都回退到"该级别均衡随机"，绝不让接口因 LLM 抽风而挂。
"""
import json

from backend.config.categories import VALID_CODES

MAX_TOTAL = 50
DEFAULT_TOTAL = 10


def _extract_json(text: str) -> dict:
    """从 LLM 输出里抠出 JSON 对象（容忍 ```json 代码块包裹）。"""
    if not text:
        raise ValueError("empty")
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("no json object")
    return json.loads(text[start : end + 1])


def _fallback_plan(level: str | None, note: str) -> dict:
    return {
        "level": level,
        "category_quotas": None,
        "total_questions": DEFAULT_TOTAL,
        "difficulty_min": None,
        "difficulty_max": None,
        "rationale": note,
    }


def _sanitize(raw: dict, level: str | None, available_codes: set[str]) -> dict:
    """校验并夹逼 LLM 方案，非法项丢弃或回退默认。"""
    out_level = raw.get("level") or level

    # 题型配额：仅保留合法且该级别可用的 code，count 夹在 1..MAX_TOTAL
    quotas = raw.get("category_quotas")
    clean_quotas: dict[str, int] = {}
    if isinstance(quotas, dict):
        for code, cnt in quotas.items():
            if code in VALID_CODES and (not available_codes or code in available_codes):
                try:
                    n = int(cnt)
                except (TypeError, ValueError):
                    continue
                n = max(1, min(n, MAX_TOTAL))
                clean_quotas[code] = n
    # 配额总数封顶
    if clean_quotas:
        while sum(clean_quotas.values()) > MAX_TOTAL:
            # 从最大配额里削，直到不超上限
            k = max(clean_quotas, key=clean_quotas.get)
            clean_quotas[k] -= 1
            if clean_quotas[k] <= 0:
                del clean_quotas[k]

    total = raw.get("total_questions")
    try:
        total = max(1, min(int(total), MAX_TOTAL))
    except (TypeError, ValueError):
        total = DEFAULT_TOTAL

    def _diff(v):
        try:
            return max(0, min(int(v), 9))
        except (TypeError, ValueError):
            return None

    dmin, dmax = _diff(raw.get("difficulty_min")), _diff(raw.get("difficulty_max"))
    if dmin is not None and dmax is not None and dmin > dmax:
        dmin, dmax = dmax, dmin

    rationale = str(raw.get("rationale") or "").strip() or "已根据你的需求组卷。"

    return {
        "level": out_level,
        "category_quotas": clean_quotas or None,
        "total_questions": total,
        "difficulty_min": dmin,
        "difficulty_max": dmax,
        "rationale": rationale,
    }


def _build_prompt(requirement, weak_points, level, available_categories) -> str:
    cats = "\n".join(f"- {c['code']}：{c['name']}" for c in available_categories) or "（无）"
    if weak_points:
        weak = "\n".join(
            f"- {w['point']}（错 {w['wrong_count']}/{w['total_count']}，错误率 {w['error_rate']}%）"
            for w in weak_points
        )
        weak_block = f"该用户的薄弱知识点（错误率高在前）：\n{weak}"
    else:
        weak_block = "该用户暂无历史错题数据（冷启动）。请按该级别均衡出题，覆盖多种题型。"

    return f"""你是 JLPT 日语考试的组卷规划师。请根据用户需求和其薄弱点，规划一套试卷的抽题方案。

目标级别：{level or '未指定，默认 N1'}
用户需求（自然语言）：{requirement}

{weak_block}

该级别可用题型（code：中文名）：
{cats}

规则：
1. 只能使用上面列出的题型 code。
2. 若用户想"针对薄弱点/查漏补缺"，请多分配错误率高的知识点相关题型的题量。
3. 题目总数控制在 1~{MAX_TOTAL}，默认 10 左右，除非用户明确指定数量。
4. 想要多题型混合时用 category_quotas 指定每种题型的题数；只要单一或不限题型时用 total_questions。
5. rationale 用一句中文向用户说明这套卷的组卷思路（会展示给用户）。

严格输出 JSON（不要任何多余文字、不要代码块围栏）：
{{
  "level": "N1",
  "category_quotas": {{"kanji_reading": 5, "context": 5}} 或 null,
  "total_questions": 10,
  "difficulty_min": null,
  "difficulty_max": null,
  "rationale": "本卷针对你的薄弱点……"
}}"""


def plan_exam(requirement: str, weak_points: list[dict], level: str | None,
              available_categories: list[dict]) -> dict:
    """产出组卷方案 dict。任何异常都回退到该级别均衡随机方案。"""
    from backend.agent.tools import _llm  # 延迟导入，避免循环依赖

    available_codes = {c["code"] for c in available_categories}
    try:
        resp = _llm().invoke(_build_prompt(requirement, weak_points, level, available_categories))
        content = resp.content if isinstance(resp.content, str) else str(resp.content)
        raw = _extract_json(content)
        return _sanitize(raw, level, available_codes)
    except Exception:
        note = (
            "AI 规划暂时不可用，已按该级别均衡随机为你出题。"
            if not weak_points else
            "AI 规划暂时不可用，已按该级别均衡随机为你出题（含薄弱点覆盖）。"
        )
        return _fallback_plan(level, note)
