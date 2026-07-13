#!/usr/bin/env python3
"""数据库迁移：为 users 表补充 is_active 列（幂等）。

用法：
    uv run python -m scripts.migrate_is_active

已存在该列时不做任何操作，可安全重复执行。
"""
import pymysql
from pymysql.cursors import DictCursor

from crawler.config import DB_CONFIG


def column_exists(cur, table: str, column: str) -> bool:
    cur.execute(
        """SELECT COUNT(*) AS c
           FROM information_schema.COLUMNS
           WHERE TABLE_SCHEMA = DATABASE()
             AND TABLE_NAME = %s AND COLUMN_NAME = %s""",
        (table, column),
    )
    return cur.fetchone()["c"] > 0


def main():
    conn = pymysql.connect(cursorclass=DictCursor, **DB_CONFIG)
    try:
        with conn.cursor() as cur:
            if column_exists(cur, "users", "is_active"):
                print("users.is_active 已存在，跳过")
                return
            cur.execute(
                """ALTER TABLE users
                   ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT TRUE
                   COMMENT '是否启用；停用后禁止登录' AFTER role"""
            )
        conn.commit()
        print("已为 users 表添加 is_active 列")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
