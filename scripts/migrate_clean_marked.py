"""清理填空题（context）被误填入 marked 的空格括号占位符。

背景：LLM 校验时对填空题偶尔把题干的空「（　　）」误写进 marked 字段，
前端按 marked 全局加下划线，导致给填空括号加了横线。
填空题（文脈規定）本就不该有划线词——它的「空」即括号，答案从选项中选填。

本脚本把 category='context' 的 marked 一律清空。幂等，可重复执行。

用法：
  uv run python scripts/migrate_clean_marked.py          # 仅预览
  uv run python scripts/migrate_clean_marked.py --apply  # 实际清理
"""
import sys

import pymysql
from pymysql.cursors import DictCursor

from crawler.config import DB_CONFIG


def main(apply: bool) -> None:
    conn = pymysql.connect(cursorclass=DictCursor, **DB_CONFIG)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT q.id, q.marked, LEFT(q.content, 60) AS content
                   FROM questions q
                   JOIN question_groups qg ON q.group_id = qg.id
                   WHERE qg.category = 'context'
                     AND q.marked IS NOT NULL AND q.marked <> ''"""
            )
            rows = cur.fetchall()
            print(f"待清理的填空题 marked：{len(rows)} 行")
            for r in rows:
                print(f"  id={r['id']:>4}  marked={r['marked']!r}  {r['content']}")

            if not rows:
                print("没有需要清理的行。")
                return
            if not apply:
                print("\n预览模式。加 --apply 实际执行。")
                return

            cur.execute(
                """UPDATE questions q
                   JOIN question_groups qg ON q.group_id = qg.id
                   SET q.marked = ''
                   WHERE qg.category = 'context'
                     AND q.marked IS NOT NULL AND q.marked <> ''"""
            )
            affected = cur.rowcount
        conn.commit()
        print(f"\n已清理 {affected} 行。")
    finally:
        conn.close()


if __name__ == "__main__":
    main(apply="--apply" in sys.argv)
