#!/usr/bin/env python3
"""创建管理员账号的命令行工具。

用法：
    uv run python -m scripts.create_admin --email admin@example.com --password yourpassword
"""
import argparse
import sys

import pymysql
from pymysql.cursors import DictCursor

from crawler.config import DB_CONFIG
from backend.utils.security import hash_password


def main():
    parser = argparse.ArgumentParser(description="创建 JLPT 管理员账号")
    parser.add_argument("--email", required=True, help="管理员邮箱")
    parser.add_argument("--password", required=True, help="密码（至少6位）")
    args = parser.parse_args()

    if len(args.password) < 6:
        print("错误：密码至少需要6位", file=sys.stderr)
        sys.exit(1)

    conn = pymysql.connect(cursorclass=DictCursor, **DB_CONFIG)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, role FROM users WHERE email = %s", (args.email,))
            existing = cur.fetchone()
            if existing:
                if existing["role"] == "admin":
                    print(f"账号 {args.email} 已是管理员，无需重复创建")
                    sys.exit(0)
                # 已存在但是 student，升级为 admin
                cur.execute(
                    "UPDATE users SET role = 'admin', hashed_password = %s WHERE email = %s",
                    (hash_password(args.password), args.email),
                )
                conn.commit()
                print(f"已将 {args.email} 升级为管理员")
            else:
                cur.execute(
                    "INSERT INTO users (email, hashed_password, role) VALUES (%s, %s, 'admin')",
                    (args.email, hash_password(args.password)),
                )
                conn.commit()
                print(f"管理员账号已创建：{args.email}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
