"""doc_dedup 模块功能测试（写入项目根目录，遵循用户对测试文件位置的要求）"""
import sys

sys.stdout.reconfigure(encoding="utf-8")

from app.services.doc_dedup import dedup_markdown, _filter_redundant_lines, _remove_duplicate_lines, _merge_similar_sections

failures = 0


def check(name, cond, detail=""):
    global failures
    status = "PASS" if cond else "FAIL"
    if not cond:
        failures += 1
    print(f"[{status}] {name} {detail}")


# ── 1. 冗余前缀行过滤 ──
c1 = "# 1 目的和范围\n\n本章依据ISO 13485标准编制\n\n本节规定产品适用范围\n\n- 支持基础率输注功能\n- 支持大剂量输注功能\n"
r1 = _filter_redundant_lines(c1)
check("冗余前缀行过滤", "本章依据ISO 13485标准编制" not in r1 and "本节规定产品适用范围" not in r1 and "- 支持基础率输注功能" in r1)

# ── 2. 精确重复行去除（保留首次出现）──
c2 = "# 2 性能指标\n\n- 输注精度：±0.05 U/h\n- 输注精度：±0.05 U/h\n- 储药器容量：200-300 U\n"
r2 = _remove_duplicate_lines(c2)
check("精确重复行去除", r2.count("输注精度") == 1 and r2.count("储药器容量") == 1)

# ── 3. 近似重复行去除（±15%长度 + 相似度>0.92）──
c3 = "# 3 风险管理\n\n- 设备采用开环控制方式，输注精度为0.05 U/h\n- 设备采用开环控制方式，输注精度为0.05U/h\n- 设备具备IPX8级防水特性\n"
r3 = _remove_duplicate_lines(c3)
check("近似重复行去除", r3.count("开环控制") == 1 and "IPX8" in r3)

# ── 4. 高相似度小节合并（保留较详细者）──
# 内容须长于 SECTION_MIN_LEN(120) 才会参与合并比较
c4 = (
    "# 4 软件需求规范\n\n"
    "### 4.1 概述\n"
    "本部分适用于贴敷式胰岛素泵软件，软件安全等级为C级，软件失效可致患者死亡，"
    "因此软件全生命周期需按照IEC 62304 Class C要求进行严格控制，确保软件需求、架构设计、"
    "详细设计、代码实现、验证与确认等各环节的文档记录完整可追溯，并经过独立评审。\n\n"
    "### 4.2 概述说明\n"
    "本部分适用于贴敷式胰岛素泵软件，软件安全等级为C级，软件失效可致患者死亡，"
    "因此软件全生命周期需按照IEC 62304 Class C要求进行严格控制，确保软件需求、架构设计、"
    "详细设计、代码实现、验证与确认等各环节的文档记录完整可追溯，并经过独立评审确认无误。\n\n"
    "### 4.3 其他\n"
    "- 蓝牙版本：BLE 5.0\n"
)
r4 = _merge_similar_sections(c4)
# 合并保留较详细者（4.2 更长，故 4.1 被删除）
check("高相似度小节合并", "### 4.1 概述" not in r4 and "### 4.2 概述说明" in r4 and "### 4.3 其他" in r4, f"(out={r4!r}...)")

# ── 5. 短小节不被误合并（<SECTION_MIN_LEN 120）──
c5 = (
    "# 5 测试\n\n"
    "### 5.1 概述\n"
    "本部分适用。\n\n"
    "### 5.2 概述说明\n"
    "本部分适用。\n"
)
r5 = _merge_similar_sections(c5)
check("短小节不误合并", "### 5.1 概述" in r5 and "### 5.2 概述说明" in r5)

# ── 6. 幂等性（重复调用结果稳定）──
sample = (
    "# 6 综述\n\n"
    "本章依据GB 9706.224标准编制\n\n"
    "### 6.1 产品组成\n"
    "- 贴敷式胰岛素泵主机\n"
    "- 贴敷式胰岛素泵主机\n"
    "- 无线通信模块（BLE 5.0）\n\n"
    "### 6.2 产品用途\n"
    "- 用于糖尿病患者持续皮下胰岛素输注治疗\n"
    "- 用于糖尿病患者持续皮下胰岛素输注治疗\n"
)
r6_once = dedup_markdown(sample)
r6_twice = dedup_markdown(r6_once)
check("幂等性", r6_once == r6_twice)
check("去重整体效果", "本章依据" not in r6_once and r6_once.count("贴敷式胰岛素泵主机") == 1 and r6_once.count("用于糖尿病患者持续皮下胰岛素输注治疗") == 1)

# ── 7. 正常内容不被过度删除 ──
c7 = (
    "# 7 风险分析\n\n"
    "### 7.1 风险识别\n"
    "- 输注过量风险：软件逻辑错误导致单次输注量超设定值，可能引发低血糖\n"
    "- 输注不足风险：管路堵塞导致输注中断，可能引发高血糖\n"
    "- 渗漏风险：储药器密封失效，导致胰岛素渗漏\n"
)
r7 = dedup_markdown(c7)
check("正常内容保留", "- 输注过量风险" in r7 and "- 输注不足风险" in r7 and "- 渗漏风险" in r7)

print(f"\n结果: {5 + 1 + 1 - failures} PASS / 7 项，失败 {failures}")
sys.exit(1 if failures else 0)
