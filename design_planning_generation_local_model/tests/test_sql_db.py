"""
test_sql_db.py - 内置领域 SQLite 数据库单元测试

覆盖:
- init_db: 建表 + 一次性种子（幂等、seed-once、seed_version 元数据）
- get_connection: mode=ro + query_only 只读（直接写库必须失败）
- _check_read_only: 白名单拦截 DML/DDL/PRAGMA / 多语句注入
- run_query: 正常查询、空结果、行数封顶、非法表名错误
- get_schema: 合法表、非法表、空表名
- list_tables: 排除 meta
- db_path: env SQL_DB_PATH 覆盖
"""
import os
import sys
import sqlite3
import pytest
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


@pytest.fixture
def seeded_db(tmp_path):
    """在临时目录初始化数据库并返回路径"""
    from app.services.sql_db import init_db
    db_file = str(tmp_path / "domain.db")
    result = init_db(db_file)
    return db_file, result


class TestInitDb:
    def test_creates_all_tables(self, seeded_db):
        from app.services.sql_db import list_tables
        db_file, _ = seeded_db
        tables = list_tables(db_file)
        expected = {"products", "standards", "materials", "components", "parameters", "risk_items"}
        assert expected.issubset(set(tables))
        # meta 表不对外暴露
        assert "meta" not in tables

    def test_seed_once(self, seeded_db):
        from app.services.sql_db import list_tables, get_schema
        db_file, _ = seeded_db
        # 种子已写入：products 应有 1 行
        schema = get_schema("products", db_file)
        assert "贴敷式胰岛素泵系统" in schema

    def test_init_db_idempotent(self, seeded_db):
        from app.services.sql_db import init_db, run_query
        db_file, _ = seeded_db
        # 第二次调用：跳过种子，返回 seed_version
        result2 = init_db(db_file)
        assert "已存在，跳过种子" in result2
        # 数据未被重复写入（单列结果无 | 分隔，取末行）
        out = run_query("SELECT COUNT(*) AS c FROM products", db_file)
        assert out.strip().splitlines()[-1].strip() == "1"

    def test_seed_version_recorded(self, seeded_db):
        import sqlite3
        db_file, _ = seeded_db
        conn = sqlite3.connect(db_file)
        try:
            row = conn.execute("SELECT value FROM meta WHERE key='seed_version'").fetchone()
            assert row and row[0]
        finally:
            conn.close()

    def test_init_db_creates_parent_dir(self, tmp_path):
        from app.services.sql_db import init_db
        nested = tmp_path / "a" / "b" / "domain.db"
        init_db(str(nested))
        assert nested.exists()


class TestReadOnlyEnforcement:
    def test_connection_is_readonly(self, seeded_db):
        """get_connection 连接直接写库必须失败（mode=ro + query_only 双保险）"""
        from app.services.sql_db import get_connection
        db_file, _ = seeded_db
        conn = get_connection(db_file)
        try:
            with pytest.raises(sqlite3.OperationalError):
                conn.execute("INSERT INTO products (product_name) VALUES ('hack')")
                conn.commit()
        finally:
            conn.close()

    def test_run_query_rejects_insert(self, seeded_db):
        from app.services.sql_db import run_query
        db_file, _ = seeded_db
        out = run_query("INSERT INTO products (product_name) VALUES ('hack')", db_file)
        assert "只读" in out or "拒绝" in out

    def test_run_query_rejects_update(self, seeded_db):
        from app.services.sql_db import run_query
        db_file, _ = seeded_db
        out = run_query("UPDATE products SET status='x'", db_file)
        assert "只读" in out or "拒绝" in out

    def test_run_query_rejects_drop(self, seeded_db):
        from app.services.sql_db import run_query
        db_file, _ = seeded_db
        out = run_query("DROP TABLE products", db_file)
        assert "只读" in out or "拒绝" in out

    def test_run_query_rejects_pragma(self, seeded_db):
        """PRAGMA 不在白名单，即便 query_only=OFF 这类写操作也拦截"""
        from app.services.sql_db import run_query
        db_file, _ = seeded_db
        out = run_query("PRAGMA query_only=OFF", db_file)
        assert "只读" in out or "拒绝" in out

    def test_run_query_rejects_multi_statement(self, seeded_db):
        """'SELECT 1; DROP TABLE products' 必须失败（sqlite 单语句限制兜底）"""
        from app.services.sql_db import run_query
        db_file, _ = seeded_db
        out = run_query("SELECT 1; DROP TABLE products", db_file)
        assert "失败" in out

    def test_empty_query_rejected(self, seeded_db):
        from app.services.sql_db import run_query
        db_file, _ = seeded_db
        out = run_query("   ", db_file)
        assert "为空" in out

    def test_run_query_select_allowed(self, seeded_db):
        from app.services.sql_db import run_query
        db_file, _ = seeded_db
        out = run_query("SELECT product_name FROM products", db_file)
        assert "贴敷式胰岛素泵系统" in out

    def test_with_clause_allowed(self, seeded_db):
        from app.services.sql_db import run_query
        db_file, _ = seeded_db
        out = run_query("WITH t AS (SELECT * FROM products) SELECT product_name FROM t", db_file)
        assert "贴敷式胰岛素泵系统" in out


class TestRunQuery:
    def test_empty_result(self, seeded_db):
        from app.services.sql_db import run_query
        db_file, _ = seeded_db
        out = run_query("SELECT * FROM products WHERE product_name='不存在'", db_file)
        assert "无匹配数据" in out

    def test_row_cap(self, tmp_path):
        """max_rows 封顶：超过部分截断"""
        from app.services.sql_db import init_db, run_query
        db_file = str(tmp_path / "cap.db")
        init_db(db_file)
        # 用写连接塞入额外行
        conn = sqlite3.connect(db_file)
        try:
            for i in range(20):
                conn.execute(
                    "INSERT INTO products (product_name, status) VALUES (?, 'x')",
                    (f"bulk-{i}",))
            conn.commit()
        finally:
            conn.close()
        out = run_query("SELECT product_name FROM products", db_file, max_rows=3)
        assert "bulk-0" in out
        assert "已截断" in out
        assert "bulk-19" not in out

    def test_sql_error_surfaced(self, seeded_db):
        from app.services.sql_db import run_query
        db_file, _ = seeded_db
        out = run_query("SELECT no_such_col FROM products", db_file)
        assert "失败" in out


class TestGetSchema:
    def test_valid_table(self, seeded_db):
        from app.services.sql_db import get_schema
        db_file, _ = seeded_db
        out = get_schema("products", db_file)
        assert "CREATE TABLE" in out
        assert "product_name" in out
        assert "前3行" in out

    def test_invalid_table(self, seeded_db):
        from app.services.sql_db import get_schema
        db_file, _ = seeded_db
        out = get_schema("no_such_table", db_file)
        assert "不存在" in out

    def test_empty_table_names(self, seeded_db):
        from app.services.sql_db import get_schema
        db_file, _ = seeded_db
        out = get_schema("   ", db_file)
        assert "未指定表名" in out


class TestDbPath:
    def test_env_override(self, tmp_path, monkeypatch):
        from app.services.sql_db import db_path
        custom = str(tmp_path / "custom.db")
        monkeypatch.setenv("SQL_DB_PATH", custom)
        assert str(db_path()) == custom

    def test_default_path(self, monkeypatch):
        from app.services.sql_db import db_path
        monkeypatch.delenv("SQL_DB_PATH", raising=False)
        assert db_path().name == "domain.db"
