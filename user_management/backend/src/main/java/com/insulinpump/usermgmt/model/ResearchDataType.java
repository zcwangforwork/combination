package com.insulinpump.usermgmt.model;

/**
 * 研发数据记录类型
 *
 * 基础 4 类：
 *   TEST_RECORD  - 测试记录（输注精度/阻塞检测/气泡检测/IPX8防水/EMC/续航等）
 *   DESIGN_PARAM - 设计参数（基础率范围/输注精度/储药器容量/防护等级/通信方式/电池续航等）
 *   EXPERIMENT   - 实验记录（原型验证/动物实验/临床前）
 *   FAILURE      - 故障记录（堵管/输注异常/通信失败/报警误触发）
 *
 * 合规扩展 5 类（III 类医疗器械注册必交）：
 *   RISK         - 风险管理数据（ISO 14971 / YY/T 0316，FMEA/FTA 条目）
 *   BIOCOMPAT    - 生物相容性数据（GB/T 16886 系列，细胞毒性/致敏/刺激/植入等）
 *   SOFTWARE_VV  - 软件验证数据（IEC 62304 / YY/T 0664，软件安全分级 A/B/C）
 *   EMC_SAFETY   - EMC/电气安全测试数据（GB 9706.1/224, YY 9706.102/108）
 *   CLINICAL     - 临床评价数据（等同性比对/临床试验/文献综述）
 *
 * 研发全流程扩展 4 类：
 *   VALIDATION   - 验证/确认数据（设计验证 DV / 过程确认 IQ/OQ/PQ / 软件确认等）
 *   MATERIAL     - 物料/来料检验数据（原材料、IQC、供应商来料）
 *   STERILIZATION- 灭菌/包装/货架寿命数据（灭菌验证、包装试验、老化试验）
 *   CHANGE       - 变更/偏差/CAPA 数据（ECR/ECN、偏差处理、纠正预防措施）
 *
 * OTHER         - 其他（前端支持自由添加自定义键值对字段）
 */
public enum ResearchDataType {
    TEST_RECORD,
    DESIGN_PARAM,
    EXPERIMENT,
    FAILURE,
    RISK,
    BIOCOMPAT,
    SOFTWARE_VV,
    EMC_SAFETY,
    CLINICAL,
    VALIDATION,
    MATERIAL,
    STERILIZATION,
    CHANGE,
    OTHER
}
