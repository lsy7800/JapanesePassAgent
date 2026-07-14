"""pytest 基建：独立测试库 + TestClient + 种子辅助。

策略
----
- 会话开始时创建独立库 `jlpt_test`，用 SHOW CREATE TABLE 从当前库克隆**完整 DDL**
  （含外键与已应用的迁移），保证测试库结构与线上一致；用完 DROP，绝不碰真实数据。
- 通过原地修改 crawler.config.DB_CONFIG["database"] 把全应用（deps.get_db 与
  chat_repo.open_conn 都实时读该 dict）重定向到测试库，无需逐一 override 依赖。
- 每个用例前 truncate 所有表，用例间互相隔离。
- 不触达 DeepSeek：持久化逻辑直接测 chat_repo，Agent LLM 路径不在单测范围。
"""
import pymysql
import pytest
from pymysql.cursors import DictCursor

from crawler.config import DB_CONFIG
from backend.utils.security import create_access_token, hash_password

TEST_DB = "jlpt_test"


def _connect(**overrides):
    cfg = {**DB_CONFIG, "cursorclass": DictCursor, **overrides}
    return pymysql.connect(**cfg)


@pytest.fixture(scope="session", autouse=True)
def _test_db():
    """建测试库→克隆结构→重定向 DB_CONFIG；会话结束 DROP 并还原。"""
    source_db = DB_CONFIG["database"]
    admin_cfg = {k: v for k, v in DB_CONFIG.items() if k != "database"}

    # 从源库抓取每张表的完整 DDL（含外键）
    conn = pymysql.connect(cursorclass=DictCursor, **admin_cfg)
    try:
        with conn.cursor() as cur:
            cur.execute(f"SHOW TABLES FROM `{source_db}`")
            tables = [next(iter(r.values())) for r in cur.fetchall()]
            ddls = []
            for t in tables:
                cur.execute(f"SHOW CREATE TABLE `{source_db}`.`{t}`")
                ddls.append(cur.fetchone()["Create Table"])

            cur.execute(f"DROP DATABASE IF EXISTS `{TEST_DB}`")
            cur.execute(f"CREATE DATABASE `{TEST_DB}` CHARACTER SET utf8mb4")
            cur.execute(f"USE `{TEST_DB}`")
            cur.execute("SET FOREIGN_KEY_CHECKS=0")
            for ddl in ddls:
                cur.execute(ddl)
            cur.execute("SET FOREIGN_KEY_CHECKS=1")
        conn.commit()
    finally:
        conn.close()

    # 重定向全应用到测试库
    original = DB_CONFIG["database"]
    DB_CONFIG["database"] = TEST_DB
    try:
        yield
    finally:
        DB_CONFIG["database"] = original
        drop = pymysql.connect(cursorclass=DictCursor, **admin_cfg)
        try:
            with drop.cursor() as cur:
                cur.execute(f"DROP DATABASE IF EXISTS `{TEST_DB}`")
            drop.commit()
        finally:
            drop.close()


@pytest.fixture(autouse=True)
def _clean_tables():
    """每个用例前清空所有表，保证隔离。"""
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SHOW TABLES")
            tables = [next(iter(r.values())) for r in cur.fetchall()]
            cur.execute("SET FOREIGN_KEY_CHECKS=0")
            for t in tables:
                cur.execute(f"TRUNCATE TABLE `{t}`")
            cur.execute("SET FOREIGN_KEY_CHECKS=1")
        conn.commit()
    finally:
        conn.close()
    yield


@pytest.fixture
def db():
    """短连接，供测试内直接读写/断言。"""
    conn = _connect()
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from backend.api.main import app

    return TestClient(app)


@pytest.fixture
def make_user(db):
    """插入用户并返回 {id, email, password, role, token, headers}。"""
    created = []

    def _make(email="student@test.com", password="pw123456", role="student", is_active=True):
        with db.cursor() as cur:
            cur.execute(
                "INSERT INTO users (email, hashed_password, role, is_active) "
                "VALUES (%s, %s, %s, %s)",
                (email, hash_password(password), role, is_active),
            )
            uid = cur.lastrowid
        db.commit()
        token = create_access_token(uid, email, role)
        info = {
            "id": uid,
            "email": email,
            "password": password,
            "role": role,
            "token": token,
            "headers": {"Authorization": f"Bearer {token}"},
        }
        created.append(info)
        return info

    return _make
