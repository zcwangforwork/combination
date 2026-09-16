"""
内置默认模板 — 验证/测试类文档的默认风格参照。

当用户未上传自己的模板时，验证/测试类文档按「报告 / 方案」两类分别以内置参考文档为
默认风格参照生成：
- 报告类（如电气安全测试报告、EMC测试报告等）→ 《发射器验证报告》
- 方案类（如性能验证方案、软件单元测试方案等）→ 《发射器验证方案》
此外，风险管理计划类文档以《风险管理计划》为默认风格参照；软件配置管理计划类文档以《软件配置管理计划》为默认风格参照。
若用户上传了模板（state["templates"] 非空），则优先使用用户模板，本默认模板不生效。
"""
import os

# 默认模板风格样例的截断长度（与用户模板风格提示的截断策略保持一致，控制 token 消耗）
DEFAULT_REFERENCE_TRUNCATE = 3000

# 内置默认模板数据文件（相对本模块），按类别区分
_REFERENCE_FILES = {
    "report": "validation_test_report_reference.md",
    "plan": "validation_test_plan_reference.md",
    "risk_management_plan": "risk_management_plan_reference.md",
    "software_config_management_plan": "software_config_management_plan_reference.md",
}

# 各类别默认模板的中文名称，用于拼装风格提示文案
_REFERENCE_LABELS = {
    "report": "《发射器验证报告》",
    "plan": "《发射器验证方案》",
    "risk_management_plan": "《风险管理计划》",
    "software_config_management_plan": "《软件配置管理计划》",
}

# 验证/测试报告类文档类型（后缀不规则的显式补充清单）。
# 以 _test_report / _verification_report / _validation_report 结尾的文档类型
# 会自动归入此类，无需在此列出。
_EXTRA_VALIDATION_TEST_REPORT_TYPES = frozenset({
    "environmental_reliability_test",              # 环境可靠性测试报告
    "sensor_calibration_validation",               # 传感器校准验证报告
    "skin_irritation_sensitization",               # 皮肤刺激/致敏试验报告
    "process_validation_iq_oq_pq",                 # 过程确认报告(IQ/OQ/PQ)
    "material_characterization_report",            # 材料物理/化学测试报告
    "biocompatibility_drug_compatibility_report",  # 生物相容性及药液相容性试验报告
    "design_verification",                         # 设计验证（通用）
    "design_validation",                           # 设计确认（通用）
})

_VALIDATION_TEST_REPORT_SUFFIXES = (
    "_test_report",
    "_verification_report",
    "_validation_report",
)

# 验证/测试方案类文档类型后缀。
# 以 _test_plan / _verification_plan / _validation_plan / _validation_protocol 结尾
# 的文档类型自动归入此类。
_VALIDATION_TEST_PLAN_SUFFIXES = (
    "_test_plan",
    "_verification_plan",
    "_validation_plan",
    "_validation_protocol",
)

# 内置默认模板全文缓存（懒加载，进程内按类别只读一次）
_default_reference_cache = {}


def is_validation_test_report(doc_type: str) -> bool:
    """判断文档类型是否为验证/测试报告类。"""
    if not doc_type:
        return False
    if doc_type in _EXTRA_VALIDATION_TEST_REPORT_TYPES:
        return True
    return doc_type.endswith(_VALIDATION_TEST_REPORT_SUFFIXES)


def is_validation_test_plan(doc_type: str) -> bool:
    """判断文档类型是否为验证/测试方案类。"""
    if not doc_type:
        return False
    return doc_type.endswith(_VALIDATION_TEST_PLAN_SUFFIXES)


def is_validation_test_doc(doc_type: str) -> bool:
    """判断文档类型是否属于验证/测试类（报告或方案）。"""
    return is_validation_test_report(doc_type) or is_validation_test_plan(doc_type)


def is_risk_management_plan(doc_type: str) -> bool:
    """判断文档类型是否为风险管理计划类。"""
    return bool(doc_type) and doc_type == "risk_management_plan"


def is_software_config_management_plan(doc_type: str) -> bool:
    """判断文档类型是否为软件配置管理计划类。"""
    return bool(doc_type) and doc_type == "software_config_management_plan"


def _category_for(doc_type: str) -> str:
    """返回 doc_type 对应的默认模板类别：report / plan / risk_management_plan / software_config_management_plan / 空字符串。"""
    if is_validation_test_report(doc_type):
        return "report"
    if is_validation_test_plan(doc_type):
        return "plan"
    if is_risk_management_plan(doc_type):
        return "risk_management_plan"
    if is_software_config_management_plan(doc_type):
        return "software_config_management_plan"
    return ""


def _load_default_reference(category: str) -> str:
    """懒加载指定类别的内置默认模板全文（进程内缓存）。"""
    if category not in _REFERENCE_FILES:
        return ""
    if _default_reference_cache.get(category) is None:
        path = os.path.join(os.path.dirname(__file__), _REFERENCE_FILES[category])
        try:
            with open(path, "r", encoding="utf-8") as f:
                _default_reference_cache[category] = f.read()
        except Exception:
            _default_reference_cache[category] = ""
    return _default_reference_cache.get(category, "")


def get_default_template_label(doc_type: str) -> str:
    """返回 doc_type 对应默认模板的中文名称（如《发射器验证报告》）；无则空字符串。"""
    category = _category_for(doc_type)
    return _REFERENCE_LABELS.get(category, "")


def get_default_template_style(doc_type: str) -> str:
    """
    返回验证/测试类文档（报告或方案）的默认风格参照文本（截断后）。

    仅当 doc_type 为验证/测试类时返回对应类别的内置默认模板原文；
    否则返回空字符串（表示无默认模板）。
    """
    category = _category_for(doc_type)
    if not category:
        return ""
    ref = _load_default_reference(category)
    if not ref:
        return ""
    return ref[:DEFAULT_REFERENCE_TRUNCATE]
