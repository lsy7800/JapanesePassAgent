import csv
import json
import os
import re
import pymysql

from crawler.config import DB_CONFIG

# 三表 DDL 见 crawler/db/schema.sql，此处内联以便一键建表。
SCHEMA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "db", "schema.sql")

# ── 幂等写入策略 ──────────────────────────────────────────────────────
# 一律按 source_ref / (group_id,seq) / (question_id,label) 做 upsert，**不删后重建**。
#
# 为什么不能删后重建：exam_items.group_id 的外键是 ON DELETE CASCADE，删掉题组会
# 连带删掉历史试卷里引用它的作答记录——试卷变成空壳或缺题。改用 upsert 后题组 id
# 保持稳定，重跑入库只更新内容，历史试卷不受影响。
#
# 注意 ON DUPLICATE KEY UPDATE 时 lastrowid 的坑：MySQL 在「命中重复键而走更新」
# 时 lastrowid 为 0（或上一次的值），不能直接用来取 id，故所有 upsert 之后都用
# SELECT 显式回查主键。

UPSERT_GROUP_SQL = """
INSERT INTO question_groups (
    type, category, article, level, exam_date, difficulty, knowledge_points, source, source_ref
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
ON DUPLICATE KEY UPDATE
    type = VALUES(type), category = VALUES(category), article = VALUES(article),
    level = VALUES(level), exam_date = VALUES(exam_date), difficulty = VALUES(difficulty),
    knowledge_points = VALUES(knowledge_points), source = VALUES(source);
"""

UPSERT_QUESTION_SQL = """
INSERT INTO questions (group_id, seq, content, marked, answer, analysis)
VALUES (%s, %s, %s, %s, %s, %s)
ON DUPLICATE KEY UPDATE
    content = VALUES(content), marked = VALUES(marked),
    answer = VALUES(answer), analysis = VALUES(analysis);
"""

UPSERT_OPTION_SQL = """
INSERT INTO options (question_id, label, content) VALUES (%s, %s, %s)
ON DUPLICATE KEY UPDATE content = VALUES(content);
"""

SELECT_GROUP_ID_SQL = "SELECT id FROM question_groups WHERE source_ref = %s;"
SELECT_SOURCE_REFS_SQL = "SELECT id, source_ref FROM question_groups WHERE source = %s;"
COUNT_EXAM_REFS_SQL = """
SELECT COUNT(DISTINCT exam_id) AS exams, COUNT(*) AS items
FROM exam_items WHERE group_id IN ({});
"""
SELECT_QUESTION_ID_SQL = "SELECT id FROM questions WHERE group_id = %s AND seq = %s;"

# 清理「本次数据里已不存在」的残留子题/选项（题型改版后子题变少的情况）
DELETE_STALE_QUESTIONS_SQL = "DELETE FROM questions WHERE group_id = %s AND seq NOT IN ({});"
DELETE_STALE_OPTIONS_SQL = "DELETE FROM options WHERE question_id = %s AND label NOT IN ({});"
DELETE_ALL_OPTIONS_SQL = "DELETE FROM options WHERE question_id = %s;"

OPTION_LABELS = ["a", "b", "c", "d"]


CSV_HEADERS = [
    "id", "content", "marked", "option_a", "option_b", "option_c", "option_d",
    "level", "answer", "date", "analysis", "difficulty", "knowledge_points",
]


def _resolve_data_path(json_path):
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if os.path.isabs(json_path):
        return json_path
    return os.path.join(project_root, "data", "raw", json_path)


def _parse_difficulty(raw):
    """difficulty 在校验数据中是字符串（如 "4"），转为 TINYINT 可接受的 int。"""
    try:
        return max(0, min(9, int(str(raw).strip())))
    except (ValueError, TypeError):
        return 0


def write_to_csv(json_path, csv_path=None):
    full_path = _resolve_data_path(json_path)

    with open(full_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if csv_path is None:
        base_name = os.path.splitext(os.path.basename(json_path))[0]
        csv_path = os.path.join(os.path.dirname(full_path), f"{base_name}.csv")

    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
        writer.writeheader()

        for item in data:
            options = item.get("options", {})
            writer.writerow({
                "id": item.get("id", ""),
                "content": item.get("content", ""),
                "marked": item.get("marked", ""),
                "option_a": options.get("a", ""),
                "option_b": options.get("b", ""),
                "option_c": options.get("c", ""),
                "option_d": options.get("d", ""),
                "level": item.get("level", ""),
                "answer": item.get("answer", ""),
                "date": item.get("date", ""),
                "analysis": item.get("analysis", ""),
                "difficulty": item.get("difficulty", ""),
                "knowledge_points": json.dumps(item.get("knowledge_points", []), ensure_ascii=False),
            })

    print(f"CSV 写入完成: {csv_path} ({len(data)} 条记录)")


def init_schema(cursor):
    """执行 schema.sql 建立三表结构。"""
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        ddl = f.read()
    for statement in ddl.split(";"):
        statement = statement.strip()
        if statement:
            cursor.execute(statement)
    print("三表结构已就绪")


def _prune_stale_groups(cursor, source, seen_refs):
    """删掉该 source 下「本次文件里已不存在」的旧题组。

    取代原先的 `DELETE FROM question_groups WHERE source=%s`（删全部再重建）：
    那样做会让每次重跑都重建题组、id 全变，触发 exam_items 的 ON DELETE CASCADE
    打穿历史试卷。现在只删真正消失的题组，正常重跑 seen_refs 覆盖全部 → 一个不删。

    若待删题组仍被试卷引用，会打印警告说明将连带丢失多少作答记录——这是有意保留的
    级联（题目确实没了，留着引用会渲染出缺题的试卷），但要让操作者看见。
    """
    cursor.execute(SELECT_SOURCE_REFS_SQL, (source,))
    rows = cursor.fetchall()
    existing = [
        (r[0], r[1]) if isinstance(r, (tuple, list)) else (r["id"], r["source_ref"])
        for r in rows
    ]
    stale = [gid for gid, ref in existing if ref not in seen_refs]
    if not stale:
        return 0

    placeholders = ", ".join(["%s"] * len(stale))
    cursor.execute(COUNT_EXAM_REFS_SQL.format(placeholders), tuple(stale))
    row = cursor.fetchone()
    exams, items = (row[0], row[1]) if isinstance(row, (tuple, list)) else (row["exams"], row["items"])
    if exams:
        print(
            f"  ⚠ 待删的 {len(stale)} 个题组仍被 {exams} 张试卷引用，"
            f"将连带删除 {items} 条作答记录（这些题目已不在源数据中）"
        )
    cursor.execute(f"DELETE FROM question_groups WHERE id IN ({placeholders});", tuple(stale))
    print(f"  已删除 {len(stale)} 个源数据中已不存在的旧题组")
    return len(stale)


def _upsert_group(cursor, sql, params, source_ref):
    """执行题组 upsert 并回查主键。

    ON DUPLICATE KEY UPDATE 走更新分支时 lastrowid 不可靠，故一律 SELECT 回查。
    """
    cursor.execute(sql, params)
    cursor.execute(SELECT_GROUP_ID_SQL, (source_ref,))
    row = cursor.fetchone()
    if not row:
        raise RuntimeError(f"题组 upsert 后回查不到 source_ref={source_ref}")
    return row[0] if isinstance(row, (tuple, list)) else row["id"]


def _upsert_question(cursor, group_id, seq, content, marked, answer, analysis):
    """执行子题 upsert 并回查主键。"""
    cursor.execute(UPSERT_QUESTION_SQL, (group_id, seq, content, marked, answer, analysis))
    cursor.execute(SELECT_QUESTION_ID_SQL, (group_id, seq))
    row = cursor.fetchone()
    if not row:
        raise RuntimeError(f"子题 upsert 后回查不到 group_id={group_id} seq={seq}")
    return row[0] if isinstance(row, (tuple, list)) else row["id"]


def _prune_questions(cursor, group_id, keep_seqs):
    """删掉该题组下本次数据未覆盖的旧子题（含其选项，靠外键级联）。

    keep_seqs 为空说明这条记录一个子题都没解析出来——几乎总是「用错了入库函数」
    （如把扁平结构的听力文件喂给了 _insert_listening_passage，它找 questions 键找不到）。
    此时清空已有子题会静默销毁数据，故直接抛错让调用方发现。
    """
    if not keep_seqs:
        raise ValueError(
            f"题组 {group_id} 本次未解析出任何子题，拒绝清空既有子题。"
            f"请检查是否用错入库函数（扁平结构用 write_listening_to_mysql，"
            f"嵌套 questions 结构用 write_listening_passage_to_mysql）"
        )
    placeholders = ", ".join(["%s"] * len(keep_seqs))
    cursor.execute(DELETE_STALE_QUESTIONS_SQL.format(placeholders), (group_id, *keep_seqs))


def _prune_options(cursor, question_id, keep_labels):
    """删掉该子题下本次数据未覆盖的旧选项（如选项数从 4 减到 3）。

    keep_labels 允许为空：源数据确实存在无选项的子题（如 result_85 有 2 条），
    这属于已知的数据缺口，不是用错函数，故不像子题那样抛错。
    """
    if keep_labels:
        placeholders = ", ".join(["%s"] * len(keep_labels))
        cursor.execute(DELETE_STALE_OPTIONS_SQL.format(placeholders), (question_id, *keep_labels))
    else:
        cursor.execute(DELETE_ALL_OPTIONS_SQL, (question_id,))


def _insert_single_choice(cursor, item, source, category=None):
    """将一条校验后的单选题数据写入三表（1 题组 → 1 子题 → 4 选项）。"""
    source_ref = f"{source}#{item.get('id')}"
    knowledge_points = json.dumps(item.get("knowledge_points", []), ensure_ascii=False)

    group_id = _upsert_group(cursor, UPSERT_GROUP_SQL, (
        "single_choice",
        category,  # JLPT 题型 code（如 paraphrase/usage），见 backend/config/categories.py
        None,  # 单选题无文章
        item.get("level", ""),
        item.get("date", ""),
        _parse_difficulty(item.get("difficulty")),
        knowledge_points,
        source,
        source_ref,
    ), source_ref)

    question_id = _upsert_question(
        cursor, group_id,
        1,  # 单选题子题顺序号固定为 1
        item.get("content", ""),
        item.get("marked", ""),
        item.get("answer", ""),
        item.get("analysis", ""),
    )
    _prune_questions(cursor, group_id, [1])

    options = item.get("options", {})
    for label in OPTION_LABELS:
        cursor.execute(UPSERT_OPTION_SQL, (question_id, label, options.get(label, "")))
    _prune_options(cursor, question_id, OPTION_LABELS)


def _insert_passage(cursor, passage, source, category, group_type):
    """通用「一篇文章 + N 子题」入库（1 题组 + article + N 子题，每子题 4 选项）。

    覆盖 cloze（完形，N 个空、子题 content 空）与 reading（阅读，N 个问句、子题 content=问句）。
    N=1 即短篇一问，N≥2 即中长篇多问，同一路径无需改动。
    难度/知识点为组级：难度取各子题均值（取整），知识点取各子题并集去重。
    子题 content 取 question 字段（完形无该字段 → 空），答案/解析逐子题写入。
    """
    source_ref = f"{source}#{passage.get('id')}"
    questions = passage.get("questions", [])

    diffs = [_parse_difficulty(q.get("difficulty")) for q in questions]
    diffs = [d for d in diffs if d > 0]
    group_diff = round(sum(diffs) / len(diffs)) if diffs else 0
    kps = []
    for q in questions:
        for kp in (q.get("knowledge_points") or []):
            if kp not in kps:
                kps.append(kp)
    knowledge_points = json.dumps(kps, ensure_ascii=False)

    group_id = _upsert_group(cursor, UPSERT_GROUP_SQL, (
        group_type,
        category,
        passage.get("article"),
        passage.get("level", ""),
        passage.get("date", ""),
        group_diff,
        knowledge_points,
        source,
        source_ref,
    ), source_ref)

    seqs = []
    for i, q in enumerate(questions, 1):
        seq = q.get("no", i)             # 子题顺序号
        seqs.append(seq)
        question_id = _upsert_question(
            cursor, group_id, seq,
            q.get("question", ""),       # content：阅读=问句；完形无此字段 → 空
            "",                          # marked 留空
            q.get("answer", ""),
            q.get("analysis", ""),
        )
        options = q.get("options", {})
        for label in OPTION_LABELS:
            cursor.execute(UPSERT_OPTION_SQL, (question_id, label, options.get(label, "")))
        _prune_options(cursor, question_id, OPTION_LABELS)
    _prune_questions(cursor, group_id, seqs)


def write_to_mysql(json_path, source=None, category=None):
    """将校验后的 JSON 数据批量写入三表结构。

    幂等策略：按 source_ref upsert（题组 id 保持稳定），最后只删源数据中已消失的旧题组。
    重复导入不会产生脏数据，也不会破坏引用这些题目的历史试卷。
    source 默认取文件名（去扩展名），如 result_67_validated。

    category: JLPT 题型 code（见 backend/config/categories.py），写入 question_groups.category，
    供线上考试/智能组卷按题型选题。同一文件应对应单一题型。
    """
    full_path = _resolve_data_path(json_path)

    if source is None:
        source = os.path.splitext(os.path.basename(json_path))[0]

    with open(full_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    conn = pymysql.connect(**DB_CONFIG)
    try:
        cursor = conn.cursor()
        init_schema(cursor)

        success = 0
        seen_refs = set()
        for item in data:
            try:
                _insert_single_choice(cursor, item, source, category)
                seen_refs.add(f"{source}#{item.get('id')}")
                success += 1
            except Exception as e:
                print(f"写入失败 ID: {item.get('id')}, 错误: {e}")

        # 只在整批都成功时清理残留：有写入失败时 seen_refs 不完整，
        # 贸然清理会把「其实还在源数据里、只是这次写失败」的题组删掉。
        if success == len(data):
            _prune_stale_groups(cursor, source, seen_refs)
        elif success:
            print(f"  ⚠ 有 {len(data) - success} 条写入失败，跳过旧题组清理以免误删")

        conn.commit()
        print(f"写入完成: 成功 {success}/{len(data)}（source={source}, category={category}）")
    finally:
        conn.close()


def _write_passages(json_path, source, category, group_type, normalize=None):
    """通用「一篇 N 问」批量入库（cloze / reading 共用），按 source_ref 幂等 upsert。

    normalize: 可选，把一条原始记录转成 {article, questions:[...]} 结构（短篇阅读用，
    因其校验产物是扁平一问）；None 表示记录本身已是嵌套结构（完形）。
    """
    full_path = _resolve_data_path(json_path)
    if source is None:
        source = os.path.splitext(os.path.basename(json_path))[0]

    with open(full_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    conn = pymysql.connect(**DB_CONFIG)
    try:
        cursor = conn.cursor()
        init_schema(cursor)

        groups = 0
        subs = 0
        seen_refs = set()
        for rec in data:
            passage = normalize(rec) if normalize else rec
            try:
                _insert_passage(cursor, passage, source, category, group_type)
                seen_refs.add(f"{source}#{passage.get('id')}")
                groups += 1
                subs += len(passage.get("questions", []))
            except Exception as e:
                print(f"写入失败 篇 ID: {passage.get('id')}, 错误: {e}")

        # 只在整批都成功时清理残留，避免把「写失败但仍在源数据里」的题组误删
        if groups == len(data):
            _prune_stale_groups(cursor, source, seen_refs)
        elif groups:
            print(f"  ⚠ 有 {len(data) - groups} 篇写入失败，跳过旧题组清理以免误删")

        conn.commit()
        print(f"写入完成: {groups}/{len(data)} 篇，共 {subs} 小题（source={source}, category={category}, type={group_type}）")
    finally:
        conn.close()


def write_passage_to_mysql(json_path, source=None, category="text_grammar"):
    """文章完形（cloze）批量入库。每篇文章 = 1 个 cloze 题组 + N 子题。"""
    _write_passages(json_path, source, category, "cloze")


def _reading_to_passage(rec):
    """短篇阅读校验产物（扁平一问）→ 通用「一篇 N 问」结构（N=1）。

    中长篇阅读若产出 {article, questions:[...]} 嵌套结构，可直接走 _write_passages 无需此转换。
    """
    return {
        "id": rec.get("id"),
        "article": rec.get("article", ""),
        "level": rec.get("level", ""),
        "date": rec.get("date", ""),
        "questions": [{
            "no": 1,
            "question": rec.get("question", ""),
            "options": rec.get("options", {}),
            "answer": rec.get("answer", ""),
            "analysis": rec.get("analysis", ""),
            "difficulty": rec.get("difficulty", ""),
            "knowledge_points": rec.get("knowledge_points", []),
        }],
    }


def write_reading_to_mysql(json_path, source=None, category="reading_short"):
    """阅读理解批量入库。

    自动检测格式：
    - 嵌套结构（含 questions 列表）→ 直接入库（中长篇/信息检索）
    - 扁平结构（单问）→ _reading_to_passage 转成 N=1 再入库（短篇）
    """
    import json as _json
    full_path = _resolve_data_path(json_path)
    with open(full_path, "r", encoding="utf-8") as f:
        sample = _json.load(f)
    # 取第一条判断格式
    first = sample[0] if sample else {}
    if isinstance(first.get("questions"), list):
        normalize = None
    else:
        normalize = _reading_to_passage
    _write_passages(json_path, source, category, "reading", normalize=normalize)


UPSERT_LISTENING_GROUP_SQL = """
INSERT INTO question_groups (
    type, category, article, audio_url, level, exam_date, difficulty, knowledge_points, source, source_ref
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON DUPLICATE KEY UPDATE
    type = VALUES(type), category = VALUES(category), article = VALUES(article),
    audio_url = VALUES(audio_url), level = VALUES(level), exam_date = VALUES(exam_date),
    difficulty = VALUES(difficulty), knowledge_points = VALUES(knowledge_points),
    source = VALUES(source);
"""


def _num_to_label(ans):
    """答案数字（'1'~'4' / 1~4）转选项字母（a~d）；已是字母则原样返回。"""
    s = str(ans).strip().lower()
    if s in OPTION_LABELS:
        return s
    if s.isdigit() and 1 <= int(s) <= len(OPTION_LABELS):
        return OPTION_LABELS[int(s) - 1]
    return ""


def _insert_listening(cursor, item, source, category):
    """听力题入库：1 题组（type=listening, article=原文脚本, audio_url）+ 1 子题 + 4 选项。

    爬虫产出扁平结构：question=设问, article=听力原文脚本, choice=选项列表,
    answer=答案数字(1~4), analysis=答案说明(可能空), audio_url=音频相对路径。
    """
    source_ref = f"{source}#{item.get('id')}"
    level = ""
    date = item.get("date", "")
    m = re.search(r"N[1-5]", date)
    if m:
        level = m.group(0)
    knowledge_points = json.dumps(item.get("knowledge_points", []), ensure_ascii=False)

    group_id = _upsert_group(cursor, UPSERT_LISTENING_GROUP_SQL, (
        "listening",
        category,
        item.get("article", ""),        # 听力原文脚本
        item.get("audio_url", ""),      # 音频相对路径
        level,
        date,
        _parse_difficulty(item.get("difficulty")),
        knowledge_points,
        source,
        source_ref,
    ), source_ref)

    question_id = _upsert_question(
        cursor, group_id,
        1,                              # 听力一段音频一问，seq 固定 1
        item.get("question", ""),       # content：设问
        "",                             # marked 留空
        _num_to_label(item.get("answer", "")),
        item.get("analysis", ""),       # 答案说明（多数为空）
    )
    _prune_questions(cursor, group_id, [1])

    # 按实际选项数写入（听力题多为 4 选，即时应答为 3 选）；不补空选项，
    # 避免前端渲染出多余的空 d 选项。
    choice = item.get("choice", []) or []
    labels = []
    for i, content in enumerate(choice[:len(OPTION_LABELS)]):
        labels.append(OPTION_LABELS[i])
        cursor.execute(UPSERT_OPTION_SQL, (question_id, OPTION_LABELS[i], content))
    _prune_options(cursor, question_id, labels)


def write_listening_to_mysql(json_path, source=None, category="task_listening"):
    """听力题批量入库，按 source 幂等替换。

    category 默认 task_listening（課題理解）；其他听力题型（point_listening 等）
    传对应 code 即可。音频只存相对路径，前端拼可配置 base 前缀播放。
    """
    full_path = _resolve_data_path(json_path)
    if source is None:
        source = os.path.splitext(os.path.basename(json_path))[0]

    with open(full_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    conn = pymysql.connect(**DB_CONFIG)
    try:
        cursor = conn.cursor()
        init_schema(cursor)

        ok = 0
        seen_refs = set()
        for item in data:
            try:
                _insert_listening(cursor, item, source, category)
                seen_refs.add(f"{source}#{item.get('id')}")
                ok += 1
            except Exception as e:
                print(f"写入失败 id: {item.get('id')}, 错误: {e}")

        # 只在整批都成功时清理残留，避免把「写失败但仍在源数据里」的题组误删
        if ok == len(data):
            _prune_stale_groups(cursor, source, seen_refs)
        elif ok:
            print(f"  ⚠ 有 {len(data) - ok} 题写入失败，跳过旧题组清理以免误删")

        conn.commit()
        print(f"写入完成: {ok}/{len(data)} 题（source={source}, category={category}, type=listening）")
    finally:
        conn.close()


def _insert_listening_passage(cursor, item, source, category):
    """综合理解等「一段音频 + N 子题」入库：1 题组（listening, article=脚本, audio_url）+ N 子题。

    嵌套结构：item = {id, audio_url, article, date, questions:[{no,question,options,answer,analysis}]}。
    子题选项为 dict（a/b/c/d）；按实际选项数写入，不补空。
    """
    source_ref = f"{source}#{item.get('id')}"
    level = ""
    m = re.search(r"N[1-5]", item.get("date", "") or "")
    if m:
        level = m.group(0)

    group_id = _upsert_group(cursor, UPSERT_LISTENING_GROUP_SQL, (
        "listening",
        category,
        item.get("article", ""),        # 听力脚本
        item.get("audio_url", ""),
        level,
        item.get("date", ""),
        0,
        json.dumps([], ensure_ascii=False),
        source,
        source_ref,
    ), source_ref)

    seqs = []
    for i, q in enumerate(item.get("questions", []), 1):
        seq = q.get("no", i)
        seqs.append(seq)
        question_id = _upsert_question(
            cursor, group_id, seq,
            q.get("question", ""),      # 题干（统合理解留空）
            "",
            _num_to_label(q.get("answer", "")),
            q.get("analysis", ""),
        )
        options = q.get("options", {}) or {}
        labels = []
        for label in OPTION_LABELS:
            if label in options and options[label]:
                labels.append(label)
                cursor.execute(UPSERT_OPTION_SQL, (question_id, label, options[label]))
        _prune_options(cursor, question_id, labels)
    _prune_questions(cursor, group_id, seqs)


def write_listening_passage_to_mysql(json_path, source=None, category="integ_listen"):
    """综合理解（一段音频 N 子题）批量入库，按 source 幂等替换。"""
    full_path = _resolve_data_path(json_path)
    if source is None:
        source = os.path.splitext(os.path.basename(json_path))[0]

    with open(full_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    conn = pymysql.connect(**DB_CONFIG)
    try:
        cursor = conn.cursor()
        init_schema(cursor)
        groups = subs = 0
        seen_refs = set()
        for item in data:
            try:
                _insert_listening_passage(cursor, item, source, category)
                seen_refs.add(f"{source}#{item.get('id')}")
                groups += 1
                subs += len(item.get("questions", []))
            except Exception as e:
                print(f"写入失败 id: {item.get('id')}, 错误: {e}")

        # 只在整批都成功时清理残留，避免把「写失败但仍在源数据里」的题组误删
        if groups == len(data):
            _prune_stale_groups(cursor, source, seen_refs)
        elif groups:
            print(f"  ⚠ 有 {len(data) - groups} 组写入失败，跳过旧题组清理以免误删")

        conn.commit()
        print(f"写入完成: {groups}/{len(data)} 组，共 {subs} 子题（source={source}, category={category}, type=listening）")
    finally:
        conn.close()


if __name__ == "__main__":
    # write_to_mysql("result_67_validated.json")
    write_to_csv("result_67_validated.json", "test.csv")
