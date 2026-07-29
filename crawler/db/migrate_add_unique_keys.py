"""一次性迁移：为 questions / options 补上 upsert 所需的唯一键。

背景：入库原先是「按 source 删全部题组再重建」，而 exam_items.group_id 的外键是
ON DELETE CASCADE——每次重跑入库都会把引用这些题目的历史试卷打穿（变成空壳或缺题）。
改成按 source_ref / (group_id,seq) / (question_id,label) upsert 后题组 id 保持稳定，
但后两个 upsert 需要对应的唯一键才能生效，故给已建好的库补上。

schema.sql 已同步加了这两个键，新建库无需跑本脚本。

用法：uv run python -m crawler.db.migrate_add_unique_keys
幂等：键已存在则跳过；发现重复数据则中止并列出，不会擅自删数据。
"""
import pymysql
from pymysql.cursors import DictCursor

from crawler.config import DB_CONFIG

MIGRATIONS = [
    {
        "table": "questions",
        "key": "uk_group_seq",
        "cols": "(group_id, seq)",
        "dup_sql": """
            SELECT group_id, seq, COUNT(*) AS n FROM questions
            GROUP BY group_id, seq HAVING COUNT(*) > 1 LIMIT 10
        """,
    },
    {
        "table": "options",
        "key": "uk_question_label",
        "cols": "(question_id, label)",
        "dup_sql": """
            SELECT question_id, label, COUNT(*) AS n FROM options
            GROUP BY question_id, label HAVING COUNT(*) > 1 LIMIT 10
        """,
    },
]


def _has_key(cur, table: str, key: str) -> bool:
    cur.execute(
        """SELECT COUNT(*) AS n FROM information_schema.statistics
           WHERE table_schema = DATABASE() AND table_name = %s AND index_name = %s""",
        (table, key),
    )
    return cur.fetchone()["n"] > 0


def migrate() -> None:
    conn = pymysql.connect(cursorclass=DictCursor, **DB_CONFIG)
    try:
        with conn.cursor() as cur:
            for m in MIGRATIONS:
                table, key = m["table"], m["key"]
                if _has_key(cur, table, key):
                    print(f"✓ {table}.{key} 已存在，跳过")
                    continue

                # 有重复就不能加唯一键。这里只报告不删除——重复数据背后可能有别的
                # 问题，交由人判断，脚本不擅自处理。
                cur.execute(m["dup_sql"])
                dups = cur.fetchall()
                if dups:
                    print(f"✗ {table} 存在重复 {m['cols']}，无法加唯一键。示例：")
                    for d in dups:
                        print("   ", d)
                    raise SystemExit(f"请先处理 {table} 的重复数据后重试")

                cur.execute(f"ALTER TABLE {table} ADD UNIQUE KEY {key} {m['cols']}")
                print(f"✓ 已为 {table} 添加唯一键 {key} {m['cols']}")
        conn.commit()
        print("\n迁移完成：重新入库将按 source_ref upsert，不再删后重建，历史试卷不受影响")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    migrate()
