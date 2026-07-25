"""JLPT 题型（大题）权威定义。

对应 JLPT 官方考试结构：语言知识（文字词汇/语法）、阅读、听力四大板块，
共 21 种大题。每种题型标注适用级别（多对多）与是否可在本应用出题。

- 听力题型需音频、阅读题型需长文章，纯文本刷题暂不支持出题（examable=False），
  但保留完整定义作为权威分类，将来数据补齐即可开放。
- category 字段即题型 code，存于 question_groups.category。
- 新增/调整题型只需改本文件，前后端从接口读取，无需建表。
"""

# 板块
SECTION_VOCAB = "vocab"      # 文字词汇
SECTION_GRAMMAR = "grammar"  # 语法
SECTION_READING = "reading"  # 阅读
SECTION_LISTENING = "listening"  # 听力

SECTION_LABELS = {
    SECTION_VOCAB: "文字词汇",
    SECTION_GRAMMAR: "语法",
    SECTION_READING: "阅读",
    SECTION_LISTENING: "听力",
}

ALL_LEVELS = ["N1", "N2", "N3", "N4", "N5"]

# 每个题型：code / 中文名 / 日文原名 / 板块 / 适用级别 / 是否可出题 / 排序
# examable=False 表示暂不支持出题（听力全部、阅读多数需长文章）。
CATEGORIES = [
    # ── 文字词汇 ──
    {"code": "kanji_reading",  "name": "汉字读法", "name_ja": "漢字読み",     "section": SECTION_VOCAB, "levels": ["N1", "N2", "N3", "N4", "N5"], "examable": True},
    {"code": "kanji_writing",  "name": "汉字书写", "name_ja": "表記",         "section": SECTION_VOCAB, "levels": ["N2", "N3", "N4", "N5"],       "examable": True},
    {"code": "word_formation", "name": "词语构成", "name_ja": "語形成",       "section": SECTION_VOCAB, "levels": ["N2"],                         "examable": True},
    {"code": "context",        "name": "前后关系", "name_ja": "文脈規定",     "section": SECTION_VOCAB, "levels": ["N1", "N2", "N3", "N4", "N5"], "examable": True},
    {"code": "paraphrase",     "name": "近义替换", "name_ja": "言い換え類義", "section": SECTION_VOCAB, "levels": ["N1", "N2", "N3", "N4", "N5"], "examable": True},
    {"code": "usage",          "name": "用法",     "name_ja": "用法",         "section": SECTION_VOCAB, "levels": ["N1", "N2", "N3", "N4"],       "examable": True},

    # ── 语法 ──
    {"code": "grammar_form",   "name": "句子语法1（语法形式判断）", "name_ja": "文の文法1（文法形式の判断）", "section": SECTION_GRAMMAR, "levels": ["N1", "N2", "N3", "N4", "N5"], "examable": True},
    {"code": "grammar_order",  "name": "句子语法2（句子组织）",     "name_ja": "文の文法2（文の組み立て）",   "section": SECTION_GRAMMAR, "levels": ["N1", "N2", "N3", "N4", "N5"], "examable": True},
    {"code": "text_grammar",   "name": "文章语法",                 "name_ja": "文章の文法",                 "section": SECTION_GRAMMAR, "levels": ["N1", "N2", "N3", "N4", "N5"], "examable": True},

    # ── 阅读 ──
    {"code": "reading_short",  "name": "内容理解（短篇）", "name_ja": "内容理解（短文）", "section": SECTION_READING, "levels": ["N1", "N2", "N3", "N4", "N5"], "examable": True},
    {"code": "reading_mid",    "name": "内容理解（中篇）", "name_ja": "内容理解（中文）", "section": SECTION_READING, "levels": ["N1", "N2", "N3", "N4", "N5"], "examable": True},
    {"code": "reading_long",   "name": "内容理解（长篇）", "name_ja": "内容理解（長文）", "section": SECTION_READING, "levels": ["N1", "N3"],                   "examable": True},
    {"code": "reading_integ",  "name": "综合理解",         "name_ja": "統合理解",         "section": SECTION_READING, "levels": ["N1", "N2"],                   "examable": True},
    {"code": "reading_thesis", "name": "论点理解（长篇）", "name_ja": "主張理解（長文）", "section": SECTION_READING, "levels": ["N1", "N2"],                   "examable": False},
    {"code": "info_search",    "name": "信息检索",         "name_ja": "情報検索",         "section": SECTION_READING, "levels": ["N1", "N2", "N3", "N4", "N5"], "examable": False},

    # ── 听力（需音频，暂不支持出题，学生端隐藏） ──
    {"code": "task_listening", "name": "问题理解", "name_ja": "課題理解",   "section": SECTION_LISTENING, "levels": ["N1", "N2", "N3", "N4", "N5"], "examable": False},
    {"code": "point_listening","name": "重点理解", "name_ja": "ポイント理解", "section": SECTION_LISTENING, "levels": ["N1", "N2", "N3", "N4", "N5"], "examable": False},
    {"code": "summary_listen", "name": "概要理解", "name_ja": "概要理解",   "section": SECTION_LISTENING, "levels": ["N1", "N2", "N3"],             "examable": False},
    {"code": "verbal_express", "name": "语言表达", "name_ja": "発話表現",   "section": SECTION_LISTENING, "levels": ["N3", "N4", "N5"],             "examable": False},
    {"code": "quick_response", "name": "即时应答", "name_ja": "即時応答",   "section": SECTION_LISTENING, "levels": ["N1", "N2", "N3", "N4", "N5"], "examable": False},
    {"code": "integ_listen",   "name": "综合理解", "name_ja": "統合理解",   "section": SECTION_LISTENING, "levels": ["N1", "N2"],                   "examable": False},
]

# code -> 定义 的索引
CATEGORY_MAP = {c["code"]: c for c in CATEGORIES}

VALID_CODES = set(CATEGORY_MAP.keys())


def get_categories(level: str | None = None, examable_only: bool = False) -> list[dict]:
    """返回题型列表，可按级别过滤、可只取支持出题的。保持 CATEGORIES 原顺序。"""
    result = []
    for c in CATEGORIES:
        if level and level not in c["levels"]:
            continue
        if examable_only and not c["examable"]:
            continue
        result.append(c)
    return result


def category_name(code: str | None) -> str:
    """题型 code 转中文名，未知或空返回原值/空串。"""
    if not code:
        return ""
    c = CATEGORY_MAP.get(code)
    return c["name"] if c else code


# code -> 在 CATEGORIES 中的序号，即 JLPT 标准题型顺序（文字词汇→语法→阅读→听力）
_CATEGORY_ORDER = {c["code"]: i for i, c in enumerate(CATEGORIES)}


def category_order(code: str | None) -> int:
    """题型的标准排序权重（越小越靠前）。未知题型排到最后。"""
    return _CATEGORY_ORDER.get(code, len(CATEGORIES))

