"""FastAPI 依赖：数据库连接。

复用 crawler.config.DB_CONFIG，每个请求获取一个 PyMySQL 连接（DictCursor），
请求结束后自动关闭。
"""
import pymysql
from pymysql.cursors import DictCursor

from crawler.config import DB_CONFIG


def get_db():
    conn = pymysql.connect(cursorclass=DictCursor, **DB_CONFIG)
    try:
        yield conn
    finally:
        conn.close()
