"""内置贴敷式胰岛素泵领域 SQLite 数据库（SQL agent 查询源）

提供:
- db_path(): 数据库文件路径解析（env SQL_DB_PATH 覆盖，默认 data/domain.db）
- get_connection(): 只读连接（uri mode=ro + 语句白名单 + query_only 双保险）
- init_db(): 建表 + 一次性种子（幂等，seed-once，含 seed_version 元数据）
- list_tables() / get_schema() / run_query(): 三个查询原语，供 agent 工具调用

安全设计（/plan-eng-review 决策）:
- 只读: 连接以 mode=ro 打开（file:...?mode=ro 必须加 uri=True），且执行层白名单
  仅放行 SELECT/WITH/EXPLAIN，任何 DML/DDL/PRAGMA 一律拒绝（防模型误写库）。
- 幂等: init_db 用 CREATE TABLE IF NOT EXISTS + 空表才 seed，重复调用安全。
- 版本化: meta 表存 seed_version，便于后续增量更新种子数据（见 TODOS.md）。

每次工具调用独立连接（try/finally 关闭），禁止模块级共享连接（并发安全）。
"""
import os
import sqlite3
from pathlib import Path
from typing import Optional

# 项目根目录: app/services/sql_db.py -> app/services -> app -> 项目根
PROJECT_ROOT = Path(__file__).parent.parent.parent

# 默认数据库路径: 项目根 / data / domain.db
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "domain.db"

# 当前种子数据版本（增量更新时递增，见 TODOS.md）
SEED_VERSION = "2026-08-11-v1"

# 语句白名单前缀（只读）：仅允许 SELECT / WITH / EXPLAIN
_READ_ONLY_PREFIXES = ("select", "with", "explain")

# 单次查询最大返回行数（防模型生成笛卡尔积重查询打爆上下文）
MAX_QUERY_ROWS = 50
# schema 工具一次最多展示的表数（防输出过大撑爆上下文）
MAX_SCHEMA_TABLES = 6

# ── 建表语句 ──

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS products (
    id                   INTEGER PRIMARY KEY,
    product_name         TEXT NOT NULL,
    product_classification TEXT,
    intended_use         TEXT,
    device_class         TEXT,
    software_class       TEXT,
    status               TEXT
);

CREATE TABLE IF NOT EXISTS standards (
    id           INTEGER PRIMARY KEY,
    standard_no  TEXT NOT NULL,
    standard_name TEXT,
    category     TEXT,
    status       TEXT,
    applies_to   TEXT
);

CREATE TABLE IF NOT EXISTS materials (
    id                   INTEGER PRIMARY KEY,
    material_name        TEXT NOT NULL,
    category             TEXT,
    biocompatibility_grade TEXT,
    application          TEXT
);

CREATE TABLE IF NOT EXISTS components (
    id              INTEGER PRIMARY KEY,
    component_name  TEXT NOT NULL,
    specification   TEXT,
    function        TEXT,
    supplier        TEXT
);

CREATE TABLE IF NOT EXISTS parameters (
    id                  INTEGER PRIMARY KEY,
    param_name          TEXT NOT NULL,
    param_value         TEXT,
    unit                TEXT,
    requirement         TEXT,
    reference_standard  TEXT
);

CREATE TABLE IF NOT EXISTS risk_items (
    id               INTEGER PRIMARY KEY,
    hazard           TEXT NOT NULL,
    severity         TEXT,
    likelihood       TEXT,
    risk_level       TEXT,
    control_measure  TEXT
);
"""

# ── 种子数据（SEED_VERSION） ──

_PRODUCTS = [
    ("贴敷式胰岛素泵系统", "贴敷式胰岛素泵", "用于糖尿病患者持续皮下胰岛素输注，模拟生理性胰岛素分泌",
     "III类有源医疗器械", "C级（软件安全性）", "设计开发阶段"),
]

_STANDARDS = [
    ("GB 9706.1-2020", "医用电气设备 第1部分：基本安全和基本性能的通用要求",
     "电气安全", "现行", "整机电气安全、机械安全、标识"),
    ("GB 9706.224-2021", "医用电气设备 第2-24部分：输液泵和输液控制器基本安全和基本性能的专用要求",
     "电气安全/专用", "现行", "输液泵输注精度、报警、电气安全专用要求"),
    ("IEC 60601-2-24:2012", "Medical electrical equipment - Part 2-24: Particular requirements for infusion pumps",
     "电气安全/专用", "现行", "输注精度（±5%）、堵管报警、流速稳定性"),
    ("YY 9706.102-2021", "医用电气设备 第1-2部分：基本安全和基本性能通用要求 并列标准：电磁兼容",
     "电磁兼容", "现行", "EMC 辐射/抗扰度试验"),
    ("IEC 62304:2006+A1:2015", "医疗器械软件 软件生命周期过程",
     "软件工程", "现行", "软件开发生命周期、软件安全性分类"),
    ("YY/T 0664-2020", "医疗器械软件 软件生存周期过程",
     "软件工程", "现行", "软件验证与确认、可追溯性"),
    ("ISO 14971:2019", "医疗器械 风险管理对医疗器械的应用",
     "风险管理", "现行", "风险管理过程、风险可接受准则"),
    ("GB/T 42062-2022", "医疗器械 风险管理对医疗器械的应用",
     "风险管理", "现行", "风险管理等同采用 ISO 14971"),
    ("ISO 13485:2016", "医疗器械 质量管理体系 用于法规的要求",
     "质量管理体系", "现行", "QMS、文件控制、记录、CAPA"),
    ("GB/T 42061-2022", "医疗器械 质量管理体系 用于法规的要求",
     "质量管理体系", "现行", "QMS 等同采用 ISO 13485"),
    ("ISO 10993-1:2018", "医疗器械生物学评价 第1部分：风险管理过程中的评价与试验",
     "生物相容性", "现行", "生物相容性评价总体框架"),
    ("ISO 10993-5:2009", "医疗器械生物学评价 第5部分：体外细胞毒性试验",
     "生物相容性", "现行", "细胞毒性试验"),
    ("ISO 10993-10:2021", "医疗器械生物学评价 第10部分：皮肤致敏及刺激试验",
     "生物相容性", "现行", "皮肤接触材料致敏与刺激评价"),
    ("IEC 62366-1:2015", "医疗器械 可用性工程对医疗器械的应用",
     "可用性工程", "现行", "可用性工程过程、使用错误预防"),
    ("GB 4793.1", "测量、控制和实验室用电气设备的安全要求",
     "电气安全", "现行", "配套检验仪器的电气安全"),
]

_MATERIALS = [
    ("聚丙烯（PP）", "高分子材料", "ISO 10993-5 细胞毒性、ISO 10993-10 刺激", "储药器、结构件"),
    ("医用级聚碳酸酯（PC）", "高分子材料", "ISO 10993 系列", "外壳、泵体"),
    ("硅胶", "弹性体", "ISO 10993 系列（皮肤接触）", "密封圈、管路、粘合贴片基底"),
    ("医用级PVC", "高分子材料", "ISO 10993 系列（血液/液体接触）", "输注管路"),
    ("医用压敏胶", "粘合剂", "ISO 10993-10 刺激与致敏（皮肤接触）", "贴敷固定贴片"),
    ("不锈钢 304", "金属", "ISO 10993 系列（植入/穿刺）", "输注针"),
    ("锂聚合物电池", "电池材料", "非直接接触（外壳隔离）", "供电模块"),
]

_COMPONENTS = [
    ("微量输注泵（蠕动式）", "输注精度 ±5%（IEC 60601-2-24）", "实现持续/大剂量胰岛素输注", "待定"),
    ("储药器", "容量 2 mL（200 U，U-100 胰岛素）", "储存胰岛素药液", "待定"),
    ("输注针", "软针/硬针可选，穿刺皮肤", "将胰岛素输注入皮下", "待定"),
    ("气泡检测传感器", "超声波检测", "检测输注管路气泡，防止空气注入", "待定"),
    ("压力传感器", "检测管路压力", "堵管/堵塞检测与报警", "待定"),
    ("BLE 无线模块", "蓝牙低功耗", "与手机 App / 血糖仪通信", "待定"),
    ("微控制器（MCU）", "低功耗 Cortex-M 系列", "输注控制、算法、报警逻辑", "待定"),
]

_PARAMETERS = [
    ("基础输注速率范围", "0.025 ~ 0.1", "U/h", "步进 0.025 U/h", "GB 9706.224 / IEC 60601-2-24"),
    ("大剂量输注范围", "0.05 ~ 25", "U", "步进 0.05 U，单次最大 25 U", "IEC 60601-2-24"),
    ("输注精度", "±5", "%", "标称流量下的长期输注精度", "IEC 60601-2-24"),
    ("储药器容量", "2", "mL", "U-100 胰岛素约 200 U", "产品技术要求"),
    ("防护等级", "IPX8", "-", "可淋浴佩戴，防水深度测试", "产品技术要求"),
    ("工作温度范围", "5 ~ 40", "℃", "在温度范围内输注精度达标", "产品技术要求"),
    ("电池续航", "≥7", "天", "标称使用条件下", "产品技术要求"),
    ("报警类型", "低药量/堵管/气泡/低电量/输注结束", "-", "均需声光报警，符合专用标准要求", "GB 9706.224"),
]

_RISK_ITEMS = [
    ("胰岛素输注过量", "高", "低", "不可接受", "输注精度控制（±5%）+ 流量监测 + 大剂量上限锁定 + 过量报警"),
    ("胰岛素输注不足（堵管）", "高", "中", "不可接受", "压力传感器堵管检测 + 声光报警 + 自动暂停输注提示"),
    ("气泡注入", "中", "低", "ALARP", "气泡检测传感器 + 气泡报警 + 软件拦截"),
    ("低药量中断治疗", "中", "中", "ALARP", "低药量报警 + 储药器余量提示 + 用户更换指引"),
    ("皮肤刺激/致敏（贴片）", "中", "中", "ALARP", "选用 ISO 10993-10 通过材料 + 皮肤刺激试验 + 佩戴指引"),
    ("电磁干扰导致输注异常", "高", "低", "不可接受", "YY 9706.102 EMC 试验 + 屏蔽设计 + 抗扰度验证"),
    ("使用错误（剂量误设）", "中", "中", "ALARP", "IEC 62366-1 可用性工程 + 剂量复核确认 + 明确提示"),
]


def db_path() -> Path:
    """解析数据库文件路径（env SQL_DB_PATH 覆盖默认 data/domain.db）"""
    override = os.getenv("SQL_DB_PATH")
    if override:
        return Path(override)
    return DEFAULT_DB_PATH


def get_connection(db_file: Optional[str] = None) -> sqlite3.Connection:
    """打开只读连接。

    - file:...?mode=ro 必须加 uri=True，否则 mode=ro 被静默忽略（/plan-eng-review 外部意见修正）
    - 追加 query_only=ON 双保险（即使 whitelist 被绕过也无法写库）
    - 每次调用独立连接，调用方负责关闭
    """
    path = Path(db_file) if db_file else db_path()
    uri = f"file:{path.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def _read_only_error(query: str) -> str:
    """构造只读违规的明确错误提示（引导模型改用 SELECT）"""
    return (
        f"只读拒绝：SQL 语句 '{query[:120]}' 不是查询语句。"
        "本数据库仅允许 SELECT / WITH / EXPLAIN 只读查询，"
        "禁止 INSERT/UPDATE/DELETE/DROP/PRAGMA 等写操作。"
    )


def _check_read_only(query: str) -> Optional[str]:
    """语句白名单检查，返回错误信息（None 表示通过）。

    仅放行以 SELECT/WITH/EXPLAIN 开头的语句。不支持多语句（分号截断为单句），
    避免通过 '; DROP TABLE' 注入写操作。
    """
    stripped = query.strip()
    if not stripped:
        return "SQL 查询为空。请提供 SELECT 查询语句。"
    # 截断为第一个分号前的单条语句，杜绝多语句注入
    first_stmt = stripped.split(";", 1)[0].strip()
    lowered = first_stmt.lower()
    if not any(lowered.startswith(p) for p in _READ_ONLY_PREFIXES):
        return _read_only_error(first_stmt)
    return None


def _open_rw(db_file: Optional[str] = None) -> sqlite3.Connection:
    """打开可写连接（仅 init_db 内部建表/种子使用，agent 工具不可触达）"""
    path = Path(db_file) if db_file else db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_file: Optional[str] = None) -> str:
    """初始化领域数据库：建表 + 一次性种子（幂等）。

    返回:
        str: 初始化结果描述（已有库则说明当前 seed_version）
    """
    conn = _open_rw(db_file)
    try:
        conn.executescript(_SCHEMA_SQL)

        # seed-once: 仅当表为空时才写入种子数据
        cur = conn.execute("SELECT COUNT(*) AS c FROM products")
        if cur.fetchone()["c"] == 0:
            conn.executemany(
                "INSERT INTO products (product_name, product_classification, intended_use, device_class, software_class, status) "
                "VALUES (?, ?, ?, ?, ?, ?)", _PRODUCTS)
            conn.executemany(
                "INSERT INTO standards (standard_no, standard_name, category, status, applies_to) "
                "VALUES (?, ?, ?, ?, ?)", _STANDARDS)
            conn.executemany(
                "INSERT INTO materials (material_name, category, biocompatibility_grade, application) "
                "VALUES (?, ?, ?, ?)", _MATERIALS)
            conn.executemany(
                "INSERT INTO components (component_name, specification, function, supplier) "
                "VALUES (?, ?, ?, ?)", _COMPONENTS)
            conn.executemany(
                "INSERT INTO parameters (param_name, param_value, unit, requirement, reference_standard) "
                "VALUES (?, ?, ?, ?, ?)", _PARAMETERS)
            conn.executemany(
                "INSERT INTO risk_items (hazard, severity, likelihood, risk_level, control_measure) "
                "VALUES (?, ?, ?, ?, ?)", _RISK_ITEMS)
            conn.execute(
                "INSERT OR REPLACE INTO meta (key, value) VALUES ('seed_version', ?)", (SEED_VERSION,))
            conn.commit()
            return f"数据库初始化完成：已创建 6 张表并写入种子数据（seed_version={SEED_VERSION}）"

        row = conn.execute("SELECT value FROM meta WHERE key='seed_version'").fetchone()
        version = row["value"] if row else "unknown"
        return f"数据库已存在，跳过种子（seed_version={version}）"
    finally:
        conn.close()


def list_tables(db_file: Optional[str] = None) -> list[str]:
    """列出领域数据库中的所有用户表名"""
    conn = get_connection(db_file)
    try:
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' "
            "AND name != 'meta' ORDER BY name")
        return [row["name"] for row in cur.fetchall()]
    finally:
        conn.close()


def get_schema(table_names: str, db_file: Optional[str] = None,
               max_tables: int = MAX_SCHEMA_TABLES) -> str:
    """返回指定表的建表 SQL + 前 3 行示例数据。

    Args:
        table_names: 逗号分隔的表名列表（应先用 list_tables 确认表存在）
        max_tables: 单次最多展示表数，防输出过大
    """
    conn = get_connection(db_file)
    try:
        valid = set(list_tables(db_file))
        wanted = [t.strip() for t in table_names.split(",") if t.strip()][:max_tables]
        if not wanted:
            return "未指定表名。请先用 sql_db_list_tables 查看可用表。"

        out = []
        for table in wanted:
            if table not in valid:
                out.append(f"错误：表 '{table}' 不存在。可用表: {', '.join(sorted(valid))}")
                continue
            row = conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
            if row and row["sql"]:
                out.append(row["sql"])
            # 前 3 行示例
            quoted = '"' + table.replace('"', '""') + '"'
            try:
                rows = conn.execute(f"SELECT * FROM {quoted} LIMIT 3").fetchall()
                if rows:
                    cols = ", ".join(rows[0].keys())
                    vals = "\n".join("  " + ", ".join(str(r[c]) for c in rows[0].keys()) for r in rows)
                    out.append(f"/* {table} 前3行:\n  {cols}\n{vals}\n*/")
            except Exception as e:
                out.append(f"/* 获取 {table} 示例数据失败: {e} */")
        return "\n\n".join(out)
    finally:
        conn.close()


def run_query(query: str, db_file: Optional[str] = None,
              max_rows: int = MAX_QUERY_ROWS) -> str:
    """执行只读 SQL 查询并返回结果。

    安全:
        - _check_read_only 白名单拦截 DML/DDL/PRAGMA（工具层强制只读）
        - 连接 mode=ro + query_only 双保险
        - 结果行数封顶 max_rows，防上下文撑爆

    Returns:
        str: 结果文本（表头 + 行），或明确错误信息
    """
    err = _check_read_only(query)
    if err:
        return f"SQL 执行失败: {err}"

    conn = get_connection(db_file)
    try:
        cur = conn.execute(query)
        rows = cur.fetchmany(max_rows + 1)
        truncated = len(rows) > max_rows
        rows = rows[:max_rows]

        if not rows:
            return "查询成功，但无匹配数据（0 行）。"
        cols = list(rows[0].keys())
        lines = [" | ".join(cols)]
        for r in rows:
            lines.append(" | ".join(str(r[c]) for c in cols))
        if truncated:
            lines.append(f"...（已截断，仅显示前 {max_rows} 行）")
        return "\n".join(lines)
    except Exception as e:
        return f"SQL 执行失败: {e}"
    finally:
        conn.close()
