#!/usr/bin/env python3
"""数据库迁移：为 question_groups 加 category 列，并回填现有批次的题型（幂等）。

用法：
    uv run python -m scripts.migrate_category

- 加列 category（若不存在）
- 回填：result_67_validated → kanji_reading（汉字读法）
        result_68_validated → context（前后关系）
  仅回填 category 为空的行，可安全重复执行。
"""
import pymysql
from pymysql.cursors import DictCursor

from crawler.config import DB_CONFIG

# 现有批次 → 题型 code 的映射（当前批次与题型严格一一对应）
SOURCE_CATEGORY = {
    "result_67_validated": "kanji_reading",
    "result_68_validated": "context",
}


def column_exists(cur, table: str, column: str) -> bool:
    cur.execute(
        """SELECT COUNT(*) AS c FROM information_schema.COLUMNS
           WHERE TABLE_SCHEMA = DATABASE()
             AND TABLE_NAME = %s AND COLUMN_NAME = %s""",
        (table, column),
    )
    return cur.fetchone()["c"] > 0


def main():
    conn = pymysql.connect(cursorclass=DictCursor, **DB_CONFIG)
    try:
        with conn.cursor() as cur:
            if not column_exists(cur, "question_groups", "category"):
                cur.execute(
                    """ALTER TABLE question_groups
                       ADD COLUMN category VARCHAR(30) DEFAULT NULL
                       COMMENT 'JLPT 题型 code' AFTER type"""
                )
                print("已添加 question_groups.category 列")
            else:
                print("question_groups.category 已存在")

            for source, code in SOURCE_CATEGORY.items():
                cur.execute(
                    """UPDATE question_groups
                       SET category = %s
                       WHERE source = %s AND (category IS NULL OR category = '')""",
                    (code, source),
                )
                print(f"回填 {source} → {code}：{cur.rowcount} 行")
        conn.commit()
        print("迁移完成")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
