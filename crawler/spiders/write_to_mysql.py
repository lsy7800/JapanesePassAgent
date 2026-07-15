import csv
import json
import os
import pymysql

from crawler.config import DB_CONFIG

# 三表 DDL 见 crawler/db/schema.sql，此处内联以便一键建表。
SCHEMA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "db", "schema.sql")

INSERT_GROUP_SQL = """
INSERT INTO question_groups (
    type, category, article, level, exam_date, difficulty, knowledge_points, source, source_ref
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s);
"""

INSERT_QUESTION_SQL = """
INSERT INTO questions (group_id, seq, content, marked, answer, analysis)
VALUES (%s, %s, %s, %s, %s, %s);
"""

INSERT_OPTION_SQL = """
INSERT INTO options (question_id, label, content) VALUES (%s, %s, %s);
"""

DELETE_SOURCE_SQL = "DELETE FROM question_groups WHERE source = %s;"

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


def _insert_single_choice(cursor, item, source, category=None):
    """将一条校验后的单选题数据写入三表（1 题组 → 1 子题 → 4 选项）。"""
    source_ref = f"{source}#{item.get('id')}"
    knowledge_points = json.dumps(item.get("knowledge_points", []), ensure_ascii=False)

    cursor.execute(INSERT_GROUP_SQL, (
        "single_choice",
        category,  # JLPT 题型 code（如 paraphrase/usage），见 backend/config/categories.py
        None,  # 单选题无文章
        item.get("level", ""),
        item.get("date", ""),
        _parse_difficulty(item.get("difficulty")),
        knowledge_points,
        source,
        source_ref,
    ))
    group_id = cursor.lastrowid

    cursor.execute(INSERT_QUESTION_SQL, (
        group_id,
        1,  # 单选题子题顺序号固定为 1
        item.get("content", ""),
        item.get("marked", ""),
        item.get("answer", ""),
        item.get("analysis", ""),
    ))
    question_id = cursor.lastrowid

    options = item.get("options", {})
    for label in OPTION_LABELS:
        cursor.execute(INSERT_OPTION_SQL, (question_id, label, options.get(label, "")))


def _insert_cloze(cursor, passage, source, category):
    """将一篇文章完形题写入三表（1 题组 + article + N 子题，每子题 4 选项）。

    难度/知识点是组级字段：难度取各空均值（取整），知识点取各空并集去重。
    子题 content 留空（题干在文章里），marked 留空。
    """
    source_ref = f"{source}#{passage.get('id')}"
    questions = passage.get("questions", [])

    # 组级难度 = 各空难度均值（忽略 0/缺失）；知识点 = 各空并集去重（保序）
    diffs = [_parse_difficulty(q.get("difficulty")) for q in questions]
    diffs = [d for d in diffs if d > 0]
    group_diff = round(sum(diffs) / len(diffs)) if diffs else 0
    kps = []
    for q in questions:
        for kp in (q.get("knowledge_points") or []):
            if kp not in kps:
                kps.append(kp)
    knowledge_points = json.dumps(kps, ensure_ascii=False)

    cursor.execute(INSERT_GROUP_SQL, (
        "cloze",
        category,
        passage.get("article"),  # 完形题存文章
        passage.get("level", ""),
        passage.get("date", ""),
        group_diff,
        knowledge_points,
        source,
        source_ref,
    ))
    group_id = cursor.lastrowid

    for i, q in enumerate(questions, 1):
        cursor.execute(INSERT_QUESTION_SQL, (
            group_id,
            q.get("no", i),   # 子题顺序号 = 空号
            "",               # content 留空（题干在文章里）
            "",               # marked 留空
            q.get("answer", ""),
            q.get("analysis", ""),
        ))
        question_id = cursor.lastrowid
        options = q.get("options", {})
        for label in OPTION_LABELS:
            cursor.execute(INSERT_OPTION_SQL, (question_id, label, options.get(label, "")))


def write_to_mysql(json_path, source=None, category=None):
    """将校验后的 JSON 数据批量写入三表结构。

    幂等策略：按 source 整批替换（先删同 source 题组，级联清理子题与选项，再重新插入），
    重复导入不会产生脏数据。source 默认取文件名（去扩展名），如 result_67_validated。

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

        # 幂等：清理该 source 的旧数据（外键 ON DELETE CASCADE 自动清理子题和选项）
        cursor.execute(DELETE_SOURCE_SQL, (source,))
        print(f"已清理来源 '{source}' 的旧数据")

        success = 0
        for item in data:
            try:
                _insert_single_choice(cursor, item, source, category)
                success += 1
            except Exception as e:
                print(f"写入失败 ID: {item.get('id')}, 错误: {e}")

        conn.commit()
        print(f"写入完成: 成功 {success}/{len(data)}（source={source}, category={category}）")
    finally:
        conn.close()


def write_passage_to_mysql(json_path, source=None, category="text_grammar"):
    """将校验后的文章完形题（嵌套结构）批量写入三表。

    与 write_to_mysql 相同的幂等策略（按 source 整批替换）。每篇文章 = 1 个 cloze 题组 +
    N 个子题；category 默认 text_grammar。
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

        cursor.execute(DELETE_SOURCE_SQL, (source,))
        print(f"已清理来源 '{source}' 的旧数据")

        groups = 0
        subs = 0
        for passage in data:
            try:
                _insert_cloze(cursor, passage, source, category)
                groups += 1
                subs += len(passage.get("questions", []))
            except Exception as e:
                print(f"写入失败 篇 ID: {passage.get('id')}, 错误: {e}")

        conn.commit()
        print(f"写入完成: {groups}/{len(data)} 篇，共 {subs} 小题（source={source}, category={category}）")
    finally:
        conn.close()


if __name__ == "__main__":
    # write_to_mysql("result_67_validated.json")
    write_to_csv("result_67_validated.json", "test.csv")
