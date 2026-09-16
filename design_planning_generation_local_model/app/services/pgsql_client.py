"""PostgreSQL 查询客户端（asyncpg，Agent 工具查询源）

提供:
- get_pool(): 异步连接池（懒加载，env 配置，应用关闭时清理）
- list_tables() / get_schema() / run_query(): 三个查询原语，供 agent 工具调用
- close_pool(): 应用关闭时释放连接池

安全设计（与 sql_db.py 一致）:
- 只读: 连接以只读事务模式运行（default_transaction_read_only=True）
- 白名单: 仅放行 SELECT/WITH/EXPLAIN，拒绝 DML/DDL
- 行数限制: MAX_QUERY_ROWS=50，防大结果集撑爆上下文
- 连接池: 复用连接，避免每次查询重建

环境变量:
- PGSQL_HOST: 主机地址（默认 localhost）
- PGSQL_PORT: 端口（默认 5432）
- PGSQL_DATABASE: 数据库名（默认 postgres）
- PGSQL_USER: 用户名（默认 postgres）
- PGSQL_PASSWORD: 密码（默认空）
- PGSQL_ENABLED: 是否启用（默认 true），设为 false 时所有工具返回"未启用"
"""
import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# 语句白名单前缀（只读）
_READ_ONLY_PREFIXES = ("select", "with", "explain")

# 单次查询最大返回行数
MAX_QUERY_ROWS = 50
# schema 工具一次最多展示的表数
MAX_SCHEMA_TABLES = 6

_pool = None


def _conn_params() -> dict:
    """从环境变量读取连接参数"""
    return {
        "host": os.getenv("PGSQL_HOST", "localhost"),
        "port": int(os.getenv("PGSQL_PORT", "5432")),
        "database": os.getenv("PGSQL_DATABASE", "postgres"),
        "user": os.getenv("PGSQL_USER", "postgres"),
        "password": os.getenv("PGSQL_PASSWORD", ""),
    }


def is_enabled() -> bool:
    return os.getenv("PGSQL_ENABLED", "true").lower() == "true"


async def get_pool():
    """获取或创建异步连接池（懒加载，进程级单例）"""
    global _pool
    if _pool is None:
        import asyncpg
        params = _conn_params()
        _pool = await asyncpg.create_pool(
            **params,
            min_size=1,
            max_size=4,
            server_settings={"default_transaction_read_only": "true"},
        )
        logger.info("[pgsql] Connection pool created: %s:%s/%s",
                     params["host"], params["port"], params["database"])
    return _pool


async def close_pool():
    """关闭连接池（应用关闭时调用）"""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
        logger.info("[pgsql] Connection pool closed")


async def list_tables() -> str:
    """列出所有用户表（排除系统表）"""
    if not is_enabled():
        return "[pgsql] PostgreSQL 未启用（PGSQL_ENABLED=false）"

    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_type = 'BASE TABLE'
                ORDER BY table_name
            """)
            tables = [r["table_name"] for r in rows]
            if not tables:
                return "[pgsql] 未找到任何用户表。"
            return "PostgreSQL 数据库中的表:\n" + "\n".join(
                f"  - {t}" for t in tables
            )
    except Exception as e:
        logger.warning("[pgsql] list_tables failed: %s", e)
        return f"[pgsql] 列出表失败: {e}"


async def get_schema(table_names: str) -> str:
    """获取指定表的列信息 + 示例数据

    Args:
        table_names: 逗号分隔的表名，如 "products,standards"
    """
    if not is_enabled():
        return "[pgsql] PostgreSQL 未启用（PGSQL_ENABLED=false）"

    if not table_names or not table_names.strip():
        return "未指定表名。请先用 pgsql_list_tables 查看可用表。"

    names = [n.strip() for n in table_names.split(",") if n.strip()]
    if not names:
        return "未指定有效表名。"

    if len(names) > MAX_SCHEMA_TABLES:
        return (
            f"一次最多查看 {MAX_SCHEMA_TABLES} 张表的结构。"
            f"请分批查询，当前请求了 {len(names)} 张表。"
        )

    try:
        pool = await get_pool()
        parts = []
        async with pool.acquire() as conn:
            for tname in names:
                # 列信息
                cols = await conn.fetch("""
                    SELECT column_name, data_type, is_nullable,
                           column_default
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = $1
                    ORDER BY ordinal_position
                """, tname)

                if not cols:
                    parts.append(f"\n### {tname}\n表不存在或无权访问。")
                    continue

                lines = [f"\n### {tname}"]
                lines.append("| 列名 | 类型 | 可空 | 默认值 |")
                lines.append("|------|------|------|--------|")
                for c in cols:
                    null_flag = "YES" if c["is_nullable"] == "YES" else "NO"
                    default = c["column_default"] or ""
                    if len(default) > 30:
                        default = default[:30] + "..."
                    lines.append(
                        f"| {c['column_name']} | {c['data_type']} "
                        f"| {null_flag} | {default} |"
                    )

                # 示例数据（前3行）
                try:
                    safe_name = f'"{tname}"'
                    samples = await conn.fetch(
                        f"SELECT * FROM {safe_name} LIMIT 3"
                    )
                    if samples:
                        lines.append(f"\n示例数据（前 {len(samples)} 行）:")
                        for i, row in enumerate(samples):
                            row_dict = dict(row)
                            row_str = ", ".join(
                                f"{k}={v}" for k, v in row_dict.items()
                            )
                            lines.append(f"  [{i+1}] {row_str}")
                except Exception as e:
                    lines.append(f"\n(无法读取示例数据: {e})")

                parts.append("\n".join(lines))

        return "\n".join(parts)

    except Exception as e:
        logger.warning("[pgsql] get_schema failed: %s", e)
        return f"[pgsql] 获取表结构失败: {e}"


async def run_query(query: str) -> str:
    """执行只读 SQL 查询（SELECT/WITH/EXPLAIN 白名单）

    Args:
        query: SQL 查询语句
    """
    if not is_enabled():
        return "[pgsql] PostgreSQL 未启用（PGSQL_ENABLED=false）"

    if not query or not query.strip():
        return "查询语句为空。"

    query = query.strip().rstrip(";")

    # 白名单检查
    prefix = query.strip().lower().split()[0] if query.strip().split() else ""
    if prefix not in _READ_ONLY_PREFIXES:
        return (
            f"[pgsql] 拒绝执行: 仅允许 SELECT/WITH/EXPLAIN 查询，"
            f"不支持 '{prefix}'。"
        )

    # 禁止分号分隔的多语句
    if ";" in query.rstrip(";"):
        return "[pgsql] 拒绝执行: 不允许在查询中使用分号。"

    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            # 设置语句超时（10 秒）
            await conn.execute("SET LOCAL statement_timeout = '10s'")

            rows = await conn.fetch(query)

            if not rows:
                return "(查询结果为空)"

            # 截断到 MAX_QUERY_ROWS
            truncated = len(rows) > MAX_QUERY_ROWS
            display_rows = rows[:MAX_QUERY_ROWS]

            # 格式化为 Markdown 表格
            columns = list(display_rows[0].keys())
            header = "| " + " | ".join(columns) + " |"
            separator = "|" + "|".join("---" for _ in columns) + "|"
            data_lines = []
            for row in display_rows:
                vals = [str(row[c]) if row[c] is not None else "NULL" for c in columns]
                data_lines.append("| " + " | ".join(vals) + " |")

            result = "\n".join([header, separator] + data_lines)

            if truncated:
                result += (
                    f"\n\n*(结果已截断，仅显示前 {MAX_QUERY_ROWS} 行，"
                    f"共 {len(rows)} 行)*"
                )

            return result

    except Exception as e:
        logger.warning("[pgsql] run_query failed: %s", e)
        error_msg = str(e)
        # 常见错误提示优化
        if "relation" in error_msg and "does not exist" in error_msg:
            return (
                f"[pgsql] 表不存在: {error_msg}\n"
                f"请先用 pgsql_schema 查看正确的表名。"
            )
        if "column" in error_msg and "does not exist" in error_msg:
            return (
                f"[pgsql] 列名错误: {error_msg}\n"
                f"请先用 pgsql_schema 查看该表的列名。"
            )
        if "statement_timeout" in error_msg.lower():
            return f"[pgsql] 查询超时（10秒），请优化查询条件或缩小范围。"
        return f"[pgsql] 查询执行失败: {error_msg}"