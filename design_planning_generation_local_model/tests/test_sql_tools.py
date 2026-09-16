"""
test_sql_tools.py - SQL 领域数据库工具的 agent 侧测试

覆盖 3 个工具（sql_db_list_tables / sql_db_schema / sql_db_query）:
- 正常返回（表名、建表结构、查询结果）
- 非法表名 / 非法 SQL 的错误分支
- 只读拦截（INSERT/DROP/PRAGMA 等写操作必须被拒）
- 工具已注册进 PHASE1_TOOLS
"""
import sys
import json
import pytest
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


@pytest.fixture(scope="module")
def ensure_db():
    """工具走默认路径，先确保领域库已初始化（幂等）"""
    from app.services.sql_db import init_db
    init_db()
    return True


class TestSqlDbListTables:
    async def test_lists_tables(self, ensure_db):
        from app.services.agent_tools import sql_db_list_tables
        out = json.loads(await sql_db_list_tables.ainvoke({}))
        assert out["status"] == "ok"
        assert set(out["tables"]) >= {"products", "standards", "materials",
                                      "components", "parameters", "risk_items"}


class TestSqlDbSchema:
    async def test_valid_table(self, ensure_db):
        from app.services.agent_tools import sql_db_schema
        out = await sql_db_schema.ainvoke({"table_names": "products"})
        assert "CREATE TABLE" in out
        assert "product_name" in out

    async def test_invalid_table_returns_error(self, ensure_db):
        from app.services.agent_tools import sql_db_schema
        out = await sql_db_schema.ainvoke({"table_names": "no_such_table"})
        assert "不存在" in out


class TestSqlDbQuery:
    async def test_successful_query(self, ensure_db):
        from app.services.agent_tools import sql_db_query
        out = await sql_db_query.ainvoke({"query": "SELECT product_name FROM products"})
        assert "贴敷式胰岛素泵系统" in out

    async def test_rejects_insert(self, ensure_db):
        from app.services.agent_tools import sql_db_query
        out = await sql_db_query.ainvoke({"query": "INSERT INTO products (product_name) VALUES ('hack')"})
        assert "只读" in out or "拒绝" in out

    async def test_rejects_drop(self, ensure_db):
        from app.services.agent_tools import sql_db_query
        out = await sql_db_query.ainvoke({"query": "DROP TABLE products"})
        assert "只读" in out or "拒绝" in out

    async def test_rejects_pragma(self, ensure_db):
        from app.services.agent_tools import sql_db_query
        out = await sql_db_query.ainvoke({"query": "PRAGMA query_only=OFF"})
        assert "只读" in out or "拒绝" in out

    async def test_sql_error_returns_error(self, ensure_db):
        from app.services.agent_tools import sql_db_query
        out = await sql_db_query.ainvoke({"query": "SELECT no_such_col FROM products"})
        assert "失败" in out

    async def test_empty_result_handled(self, ensure_db):
        from app.services.agent_tools import sql_db_query
        out = await sql_db_query.ainvoke({"query": "SELECT * FROM products WHERE product_name='不存在'"})
        assert "无匹配数据" in out


class TestToolRegistration:
    def test_sql_tools_in_phase1(self):
        from app.services.agent_tools import PHASE1_TOOLS
        names = {getattr(t, "name", "") for t in PHASE1_TOOLS}
        assert "sql_db_list_tables" in names
        assert "sql_db_schema" in names
        assert "sql_db_query" in names
