#!/usr/bin/env python3
"""数据库迁移：创建对话持久化所需的 chat_sessions / chat_messages 表（幂等）。

用法：
    uv run python -m scripts.migrate_chat

- chat_sessions：一个用户的一次对话会话
- chat_messages：会话下的消息（user / assistant），删除会话时级联删除
可安全重复执行（仅在表不存在时创建）。
"""
import pymysql
from pymysql.cursors import DictCursor

from crawler.config import DB_CONFIG


def table_exists(cur, table: str) -> bool:
    cur.execute(
        """SELECT COUNT(*) AS c FROM information_schema.TABLES
           WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s""",
        (table,),
    )
    return cur.fetchone()["c"] > 0


def main():
    conn = pymysql.connect(cursorclass=DictCursor, **DB_CONFIG)
    try:
        with conn.cursor() as cur:
            if not table_exists(cur, "chat_sessions"):
                cur.execute(
                    """
                    CREATE TABLE chat_sessions (
                        id          BIGINT AUTO_INCREMENT PRIMARY KEY,
                        user_id     BIGINT NOT NULL,
                        title       VARCHAR(120) NOT NULL DEFAULT '新对话',
                        created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        updated_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                                        ON UPDATE CURRENT_TIMESTAMP,
                        INDEX idx_user_updated (user_id, updated_at DESC)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """
                )
                print("已创建表 chat_sessions")
            else:
                print("chat_sessions 已存在，跳过")

            if not table_exists(cur, "chat_messages"):
                cur.execute(
                    """
                    CREATE TABLE chat_messages (
                        id          BIGINT AUTO_INCREMENT PRIMARY KEY,
                        session_id  BIGINT NOT NULL,
                        role        ENUM('user', 'assistant') NOT NULL,
                        content     MEDIUMTEXT NOT NULL,
                        created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        INDEX idx_session (session_id, id),
                        CONSTRAINT fk_msg_session FOREIGN KEY (session_id)
                            REFERENCES chat_sessions (id) ON DELETE CASCADE
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """
                )
                print("已创建表 chat_messages")
            else:
                print("chat_messages 已存在，跳过")
        conn.commit()
        print("迁移完成")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
