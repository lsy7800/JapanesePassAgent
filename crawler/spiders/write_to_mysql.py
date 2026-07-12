import csv
import json
import os
import pymysql

from crawler.config import DB_CONFIG

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS questions (
    id INT PRIMARY KEY,
    content TEXT NOT NULL,
    marked VARCHAR(255) DEFAULT '',
    option_a VARCHAR(255) NOT NULL DEFAULT '',
    option_b VARCHAR(255) NOT NULL DEFAULT '',
    option_c VARCHAR(255) NOT NULL DEFAULT '',
    option_d VARCHAR(255) NOT NULL DEFAULT '',
    level VARCHAR(10) DEFAULT '',
    answer VARCHAR(10) NOT NULL DEFAULT '',
    date VARCHAR(20) DEFAULT '',
    analysis TEXT,
    difficulty VARCHAR(10) DEFAULT '',
    knowledge_points JSON
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""

INSERT_SQL = """
INSERT INTO questions (
    id, content, marked, option_a, option_b, option_c, option_d,
    level, answer, date, analysis, difficulty,
    knowledge_points
) VALUES (
    %s, %s, %s, %s, %s, %s, %s,
    %s, %s, %s, %s, %s, %s
)
ON DUPLICATE KEY UPDATE
    content = VALUES(content),
    marked = VALUES(marked),
    option_a = VALUES(option_a),
    option_b = VALUES(option_b),
    option_c = VALUES(option_c),
    option_d = VALUES(option_d),
    level = VALUES(level),
    answer = VALUES(answer),
    date = VALUES(date),
    analysis = VALUES(analysis),
    difficulty = VALUES(difficulty),
    knowledge_points = VALUES(knowledge_points);
"""


CSV_HEADERS = [
    "id", "content", "marked", "option_a", "option_b", "option_c", "option_d",
    "level", "answer", "date", "analysis", "difficulty", "knowledge_points",
]


def write_to_csv(json_path, csv_path=None):
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    full_path = os.path.join(project_root, "data", "raw", json_path) if not os.path.isabs(json_path) else json_path

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


def write_to_mysql(json_path):
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    full_path = os.path.join(project_root, "data", "raw", json_path) if not os.path.isabs(json_path) else json_path

    with open(full_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor()

    cursor.execute(CREATE_TABLE_SQL)
    print("表已就绪")

    success = 0
    for item in data:
        try:
            options = item.get("options", {})
            knowledge_points = json.dumps(item.get("knowledge_points", []), ensure_ascii=False)

            cursor.execute(INSERT_SQL, (
                item.get("id"),
                item.get("content", ""),
                item.get("marked", ""),
                options.get("a", ""),
                options.get("b", ""),
                options.get("c", ""),
                options.get("d", ""),
                item.get("level", ""),
                item.get("answer", ""),
                item.get("date", ""),
                item.get("analysis", ""),
                item.get("difficulty", ""),
                knowledge_points,
            ))
            success += 1
        except Exception as e:
            print(f"写入失败 ID: {item.get('id')}, 错误: {e}")

    conn.commit()
    print(f"写入完成: 成功 {success}/{len(data)}")
    cursor.close()
    conn.close()


if __name__ == "__main__":
    # write_to_mysql("result_67_validated.json")
    write_to_csv("result_67_validated.json","test.csv")