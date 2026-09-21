"""
文档类型公共常量 — DOC_TYPES 列表和 doc_type_labels 映射
贴敷式胰岛素泵（Patch Insulin Pump）全生命周期文档类型
覆盖9大阶段：设计策划、设计输入、设计输出、设计验证、设计确认、设计转化、生产制造、注册申报、上市后
"""

# ======================== 全部文档类型 ========================

DOC_TYPES = [
    # ========== 一、设计策划阶段 (Design Planning) — 10份 ==========
    "design_development_plan",           # 项目开发计划书
    "product_requirements_spec",         # 产品需求规格书(PRS)
    "risk_management_plan",              # 风险管理计划
    "software_development_plan",         # 软件开发生命周期计划
    "usability_engineering_plan",        # 可用性工程计划
    "biological_evaluation_plan",        # 生物学评价计划
    "sterilization_validation_plan",     # 灭菌验证计划
    "packaging_validation_plan",         # 包装验证计划
    "supplier_management_plan",          # 供应商管理计划
    "regulatory_strategy_document",      # 注册策略文件

    # ========== 二、设计输入阶段 (Design Input) — 6份 ==========
    "design_input",                      # 设计输入文件
    "software_requirements_spec",        # 软件需求规格书(SRS)
    "hardware_requirements_spec",        # 硬件需求规格书
    "ui_requirements_spec",              # 用户界面需求规格书
    "cybersecurity_requirements",        # 网络安全需求规格书
    "labeling_ifu_requirements",         # 标签和说明书需求
    "usability_specification",           # 可用性规范文件

    # ========== 三、设计输出阶段 (Design Output) — 12份 ==========
    "product_drawings",                  # 产品图纸
    "bill_of_materials",                 # 物料清单(BOM)
    "product_specification",             # 产品规格书
    "software_architecture_doc",         # 软件架构文档
    "software_detailed_design",          # 软件详细设计文档
    "hardware_design_doc",               # 硬件设计文档
    "firmware_design_doc",               # 固件设计文档
    "industrial_design_doc",             # 工业设计文档
    "label_nameplate_artwork",           # 标签/铭牌设计稿
    "packaging_design_artwork",          # 包装设计稿
    "instruction_for_use",               # 说明书/用户手册(IFU)
    "manufacturing_process_draft",       # 生产工艺文件(草案)

    # ========== 四、设计验证阶段 (Design Verification) — 17份 ==========
    "design_verification_master_plan",   # 设计验证总计划
    "electrical_safety_test_report",     # 电气安全测试报告
    "emc_test_report",                   # EMC测试报告
    "alarm_system_test_report",          # 报警系统测试报告
    "infusion_accuracy_test_report",     # 输注精度测试报告
    "software_unit_test_report",         # 软件单元测试报告
    "software_integration_test_report",  # 软件集成测试报告
    "software_system_test_report",       # 软件系统测试报告
    "battery_performance_test_report",   # 电池性能测试报告
    "ip_rating_test_report",             # 防水防尘测试报告(IP)
    "environmental_reliability_test",    # 环境可靠性测试报告
    "package_transport_test_report",     # 包装运输测试报告
    "seal_integrity_test_report",        # 密封完整性测试报告
    "material_characterization_report",  # 材料物理/化学测试报告
    "accelerated_aging_test_report",     # 加速老化测试报告
    "sensor_calibration_validation",     # 传感器校准验证报告
    "cybersecurity_test_report",         # 网络安全测试报告

    # ========== 五、设计确认阶段 (Design Validation) — 11份 ==========
    "design_validation_master_plan",     # 设计确认总计划
    "summative_usability_report",        # 总结性可用性工程报告
    "clinical_evaluation_report",        # 临床评价报告(CER)
    "biological_evaluation_report",      # 生物学评价报告
    "cytotoxicity_test_report",          # 细胞毒性试验报告
    "skin_irritation_sensitization",     # 皮肤刺激/致敏试验报告
    "blood_compatibility_test_report",   # 血液相容性试验报告
    "sal_validation_report",             # 无菌保证水平验证报告(SAL)
    "sterilization_residue_test_report", # 灭菌残留测试报告
    "process_validation_iq_oq_pq",       # 过程确认报告(IQ/OQ/PQ)
    "cleaning_validation_report",        # 清洗验证报告

    # ========== 六、设计转化阶段 (Design Transfer) — 7份 ==========
    "design_transfer_plan",              # 设计转化计划
    "design_transfer_report",            # 设计转化报告
    "device_master_record",              # 医疗器械主记录(DMR)
    "manufacturing_sop",                 # 生产工艺SOP
    "inspection_sop",                    # 检验SOP
    "equipment_operation_procedures",    # 设备操作规程
    "work_environment_control_doc",      # 工作环境控制文件

    # ========== 七、生产制造阶段 (Production) — 10份 ==========
    "batch_production_record",           # 批生产记录(BPR)
    "batch_inspection_record",           # 批检验记录
    "device_history_record",             # 器械历史记录(DHR)
    "incoming_inspection_records",       # 进货检验记录
    "supplier_audit_reports",            # 供应商审核报告
    "calibration_records",               # 校准记录
    "environmental_monitoring_records",  # 环境监测记录
    "nonconforming_product_records",     # 不合格品处理记录
    "sterilization_process_records",     # 灭菌过程记录
    "udi_assignment_records",            # UDI赋码记录

    # ========== 八、注册申报阶段 (Registration) — 10份 ==========
    "registration_dossier",              # 产品注册申报资料
    "product_technical_requirements",    # 产品技术要求
    "risk_management_report",            # 风险管理报告
    "essential_safety_conformity",       # 基本安全和基本性能符合性声明
    "software_version_description",      # 软件版本描述文档
    "cybersecurity_disclosure",          # 网络安全披露文档
    "clinical_evaluation_report_reg",    # 临床评价报告(注册用)
    "ifu_labeling_for_registration",     # 说明书/标签审核稿(注册用)
    "declaration_of_conformity",         # 符合性声明(DoC)
    "qms_certificate_proof",             # 质量管理体系证明文件

    # ========== 九、上市后阶段 (Post-Market) — 11份 ==========
    "pms_plan",                          # 上市后监管计划(PMS Plan)
    "pmcf_plan",                         # 上市后临床跟踪计划(PMCF Plan)
    "complaint_handling_records",        # 投诉处理记录
    "adverse_event_reports",             # 不良事件报告
    "periodic_safety_update_report",     # 定期安全更新报告(PSUR)
    "capa_records",                      # 纠正和预防措施记录(CAPA)
    "change_control_records",            # 变更控制记录
    "recall_field_safety_notice",        # 产品召回/现场安全通知记录
    "management_review_report",          # 管理评审报告
    "internal_audit_reports",            # 内部审核报告
    "pms_report",                        # 上市后监管报告(PMS Report)

    # ========== 一、设计策划阶段 扩充（DHF清单） ==========
    "market_research_product_definition",  # 市场调研与产品定义报告
    "project_feasibility_study",  # 项目可行性研究报告
    "patent_analysis_report",  # 专利分析报告
    "project_approval_review",  # 立项评审记录

    # ========== 二、设计输入阶段 扩充（DHF清单） ==========
    "user_needs_specification",  # 用户需求规格书
    "preliminary_risk_analysis",  # 初步风险分析报告
    "product_risk_analysis_matrix",  # 产品风险分析和管理总表
    "cybersecurity_risk_analysis_matrix",  # 网络安全风险分析和管理总表
    "software_config_management_plan",  # 软件配置管理计划
    "structural_design_requirements",  # 结构设计需求规格书
    "packaging_labeling_requirements",  # 包装及标识设计需求
    "product_rtm",  # 产品需求追溯矩阵(RTM)
    "software_rtm",  # 软件开发追溯表
    "cybersecurity_traceability_matrix",  # 网络安全追溯表
    "essential_principles_checklist",  # 医疗器械安全和性能基本原则（EP）清单
    "software_development_plan_di",  # 软件开发计划（设计输入阶段引用）

    # ========== 三、设计输出阶段 扩充（DHF清单） ==========
    "hardware_design_plan",  # 硬件设计方案
    "structural_design_plan",  # 结构设计方案
    "software_coding_standard",  # 软件编码规范
    "packaging_labeling_design_plan",  # 包装及标识设计方案
    "primary_packaging_material_report",  # 初包装材料选择与确认报告
    "performance_research_records",  # 性能研究相关记录
    "inspection_method_validation",  # 检验方法学验证方案及报告
    "material_specification_drawing",  # 物料规格书及图纸
    "process_flow_diagram",  # 工艺流程图
    "tooling_drawing_acceptance",  # 工装图纸及验收记录
    "approved_supplier_list",  # 合格供应商清单
    "design_output_checklist",  # 设计输出清单

    # ========== 四、设计验证阶段 扩充（DHF清单） ==========
    "performance_verification_plan",  # 性能验证方案
    "performance_verification_report",  # 性能验证报告
    "software_unit_test_plan",  # 软件单元测试方案
    "software_integration_test_plan",  # 软件集成测试方案
    "software_system_test_plan",  # 软件系统测试方案
    "software_quality_test_plan",  # 软件质量测试方案
    "software_quality_test_report",  # 软件质量测试报告
    "cybersecurity_test_plan",  # 网络安全测试方案
    "software_interface_security_test_plan",  # 软件接口网络安全测试方案
    "software_interface_security_test_report",  # 软件接口网络安全测试报告
    "packaging_verification_plan",  # 包装及标识验证方案
    "packaging_verification_report",  # 包装及标识验证报告
    "service_life_verification_plan",  # 使用期限验证方案
    "service_life_verification_report",  # 使用期限验证报告
    "shelf_life_verification_plan",  # 货架有效期验证方案
    "shelf_life_verification_report",  # 货架有效期验证报告
    "transport_verification_plan",  # 包装运输验证方案
    "leachables_test_plan",  # 可沥滤物测试方案
    "leachables_test_report",  # 可沥滤物测试报告
    "biocompatibility_drug_compatibility_report",  # 生物相容性及药液相容性试验报告
    "safety_emc_reliability_test_report",  # 安规EMC环境可靠性强制检测报告
    "registration_type_test_report",  # 注册检验报告

    # ========== 六、设计转化阶段 扩充（DHF清单） ==========
    "process_validation_plan",  # 工艺验证计划
    "sterilization_validation_protocol",  # 灭菌确认方案
    "sterilization_validation_report",  # 灭菌确认报告
    "process_validation_report",  # 工艺验证报告 (DHF row 89)

    # ========== 五、设计确认阶段 扩充（DHF清单） ==========
    "clinical_trial_plan",  # 临床试验方案
    "clinical_trial_report",  # 临床试验报告
    "usability_test_plan",  # 可用性测试方案
    "usability_test_report",  # 可用性测试报告
    "usability_validation_confirmation_report",  # 可用性验证和确认报告
    "design_validation_report",  # 设计确认报告 (DHF row 93)
    # ========== 保留原有兼容类型（映射到新类型） ==========
    "design_output",                     # 设计输出（通用）
    "design_review",                     # 设计评审
    "design_verification",               # 设计验证（通用）
    "design_validation",                 # 设计确认（通用）
    "design_change",                     # 设计变更
    "design_history_file",               # 设计历史文件(DHF)
    "fmea_analysis",                     # FMEA分析报告
    "risk_acceptance_criteria",          # 风险可接受准则
    "periodic_risk_evaluation",          # 定期风险评价报告
    "sop",                               # 作业指导书(SOP)（通用）
]

# 去重
DOC_TYPES = list(dict.fromkeys(DOC_TYPES))

# ======================== 文档类型中文标签 ========================

DOC_TYPE_LABELS = {
    # 一、设计策划阶段
    "design_development_plan": "项目开发计划书",
    "product_requirements_spec": "产品需求规格书(PRS)",
    "risk_management_plan": "风险管理计划",
    "software_development_plan": "软件开发生命周期计划",
    "usability_engineering_plan": "可用性工程计划",
    "biological_evaluation_plan": "生物学评价计划",
    "sterilization_validation_plan": "灭菌验证计划",
    "packaging_validation_plan": "包装验证计划",
    "supplier_management_plan": "供应商管理计划",
    "regulatory_strategy_document": "注册策略文件",

    # 二、设计输入阶段
    "design_input": "设计输入文件",
    "software_requirements_spec": "软件需求规格书(SRS)",
    "hardware_requirements_spec": "硬件需求规格书",
    "ui_requirements_spec": "用户界面需求规格书",
    "cybersecurity_requirements": "网络安全需求规格书",
    "labeling_ifu_requirements": "标签和说明书需求",
    "usability_specification": "可用性规范文件",

    # 三、设计输出阶段
    "product_drawings": "产品图纸",
    "bill_of_materials": "物料清单(BOM)",
    "product_specification": "产品规格书",
    "software_architecture_doc": "软件架构文档",
    "software_detailed_design": "软件详细设计文档",
    "hardware_design_doc": "硬件设计文档",
    "firmware_design_doc": "固件设计文档",
    "industrial_design_doc": "工业设计文档",
    "label_nameplate_artwork": "标签/铭牌设计稿",
    "packaging_design_artwork": "包装设计稿",
    "instruction_for_use": "说明书/用户手册(IFU)",
    "manufacturing_process_draft": "生产工艺文件(草案)",

    # 四、设计验证阶段
    "design_verification_master_plan": "设计验证总计划",
    "electrical_safety_test_report": "电气安全测试报告",
    "emc_test_report": "EMC测试报告",
    "alarm_system_test_report": "报警系统测试报告",
    "infusion_accuracy_test_report": "输注精度测试报告",
    "software_unit_test_report": "软件单元测试报告",
    "software_integration_test_report": "软件集成测试报告",
    "software_system_test_report": "软件系统测试报告",
    "battery_performance_test_report": "电池性能测试报告",
    "ip_rating_test_report": "防水防尘测试报告(IP)",
    "environmental_reliability_test": "环境可靠性测试报告",
    "package_transport_test_report": "包装运输测试报告",
    "seal_integrity_test_report": "密封完整性测试报告",
    "material_characterization_report": "材料物理/化学测试报告",
    "accelerated_aging_test_report": "加速老化测试报告",
    "sensor_calibration_validation": "传感器校准验证报告",
    "cybersecurity_test_report": "网络安全测试报告",

    # 五、设计确认阶段
    "design_validation_master_plan": "设计确认总计划",
    "summative_usability_report": "总结性可用性工程报告",
    "clinical_evaluation_report": "临床评价报告(CER)",
    "biological_evaluation_report": "生物学评价报告",
    "cytotoxicity_test_report": "细胞毒性试验报告",
    "skin_irritation_sensitization": "皮肤刺激/致敏试验报告",
    "blood_compatibility_test_report": "血液相容性试验报告",
    "sal_validation_report": "无菌保证水平验证报告(SAL)",
    "sterilization_residue_test_report": "灭菌残留测试报告",
    "process_validation_iq_oq_pq": "过程确认报告(IQ/OQ/PQ)",
    "cleaning_validation_report": "清洗验证报告",

    # 六、设计转化阶段
    "design_transfer_plan": "设计转化计划",
    "design_transfer_report": "设计转化报告",
    "device_master_record": "医疗器械主记录(DMR)",
    "manufacturing_sop": "生产工艺SOP",
    "inspection_sop": "检验SOP",
    "equipment_operation_procedures": "设备操作规程",
    "work_environment_control_doc": "工作环境控制文件",

    # 七、生产制造阶段
    "batch_production_record": "批生产记录(BPR)",
    "batch_inspection_record": "批检验记录",
    "device_history_record": "器械历史记录(DHR)",
    "incoming_inspection_records": "进货检验记录",
    "supplier_audit_reports": "供应商审核报告",
    "calibration_records": "校准记录",
    "environmental_monitoring_records": "环境监测记录",
    "nonconforming_product_records": "不合格品处理记录",
    "sterilization_process_records": "灭菌过程记录",
    "udi_assignment_records": "UDI赋码记录",

    # 八、注册申报阶段
    "registration_dossier": "产品注册申报资料",
    "product_technical_requirements": "产品技术要求",
    "risk_management_report": "风险管理报告",
    "essential_safety_conformity": "基本安全和基本性能符合性声明",
    "software_version_description": "软件版本描述文档",
    "cybersecurity_disclosure": "网络安全披露文档",
    "clinical_evaluation_report_reg": "临床评价报告(注册用)",
    "ifu_labeling_for_registration": "说明书/标签审核稿(注册用)",
    "declaration_of_conformity": "符合性声明(DoC)",
    "qms_certificate_proof": "质量管理体系证明文件",

    # 九、上市后阶段
    "pms_plan": "上市后监管计划(PMS Plan)",
    "pmcf_plan": "上市后临床跟踪计划(PMCF Plan)",
    "complaint_handling_records": "投诉处理记录",
    "adverse_event_reports": "不良事件报告",
    "periodic_safety_update_report": "定期安全更新报告(PSUR)",
    "capa_records": "纠正和预防措施记录(CAPA)",
    "change_control_records": "变更控制记录",
    "recall_field_safety_notice": "产品召回/现场安全通知记录",
    "management_review_report": "管理评审报告",
    "internal_audit_reports": "内部审核报告",
    "pms_report": "上市后监管报告(PMS Report)",

    # 一、设计策划阶段 扩充（DHF清单）
    "market_research_product_definition": "市场调研与产品定义报告",
    "project_feasibility_study": "项目可行性研究报告",
    "patent_analysis_report": "专利分析报告",
    "project_approval_review": "立项评审记录",

    # 二、设计输入阶段 扩充（DHF清单）
    "user_needs_specification": "用户需求规格书",
    "preliminary_risk_analysis": "初步风险分析报告",
    "product_risk_analysis_matrix": "产品风险分析和管理总表",
    "cybersecurity_risk_analysis_matrix": "网络安全风险分析和管理总表",
    "software_config_management_plan": "软件配置管理计划",
    "structural_design_requirements": "结构设计需求规格书",
    "packaging_labeling_requirements": "包装及标识设计需求",
    "product_rtm": "产品需求追溯矩阵(RTM)",
    "software_rtm": "软件开发追溯表",
    "cybersecurity_traceability_matrix": "网络安全追溯表",
    "essential_principles_checklist": "医疗器械安全和性能基本原则（EP）清单",
    "software_development_plan_di": "软件开发计划",

    # 三、设计输出阶段 扩充（DHF清单）
    "hardware_design_plan": "硬件设计方案",
    "structural_design_plan": "结构设计方案",
    "software_coding_standard": "软件编码规范",
    "packaging_labeling_design_plan": "包装及标识设计方案",
    "primary_packaging_material_report": "初包装材料选择与确认报告",
    "performance_research_records": "性能研究相关记录",
    "inspection_method_validation": "检验方法学验证方案及报告",
    "material_specification_drawing": "物料规格书及图纸",
    "process_flow_diagram": "工艺流程图",
    "tooling_drawing_acceptance": "工装图纸及验收记录",
    "approved_supplier_list": "合格供应商清单",
    "design_output_checklist": "设计输出清单",

    # 四、设计验证阶段 扩充（DHF清单）
    "performance_verification_plan": "性能验证方案",
    "performance_verification_report": "性能验证报告",
    "software_unit_test_plan": "软件单元测试方案",
    "software_integration_test_plan": "软件集成测试方案",
    "software_system_test_plan": "软件系统测试方案",
    "software_quality_test_plan": "软件质量测试方案",
    "software_quality_test_report": "软件质量测试报告",
    "cybersecurity_test_plan": "网络安全测试方案",
    "software_interface_security_test_plan": "软件接口网络安全测试方案",
    "software_interface_security_test_report": "软件接口网络安全测试报告",
    "packaging_verification_plan": "包装及标识验证方案",
    "packaging_verification_report": "包装及标识验证报告",
    "service_life_verification_plan": "使用期限验证方案",
    "service_life_verification_report": "使用期限验证报告",
    "shelf_life_verification_plan": "货架有效期验证方案",
    "shelf_life_verification_report": "货架有效期验证报告",
    "transport_verification_plan": "包装运输验证方案",
    "leachables_test_plan": "可沥滤物测试方案",
    "leachables_test_report": "可沥滤物测试报告",
    "biocompatibility_drug_compatibility_report": "生物相容性及药液相容性试验报告",
    "safety_emc_reliability_test_report": "安规EMC环境可靠性强制检测报告",
    "registration_type_test_report": "注册检验报告",

    # 六、设计转化阶段 扩充（DHF清单）
    "process_validation_plan": "工艺验证计划",
    "sterilization_validation_protocol": "灭菌确认方案",
    "sterilization_validation_report": "灭菌确认报告",
    "process_validation_report": "工艺验证报告",

    # 五、设计确认阶段 扩充（DHF清单）
    "clinical_trial_plan": "临床试验方案",
    "clinical_trial_report": "临床试验报告",
    "usability_test_plan": "可用性测试方案",
    "usability_test_report": "可用性测试报告",
    "usability_validation_confirmation_report": "可用性验证和确认报告",
    "design_validation_report": "设计确认报告",
    # 保留原有兼容类型
    "design_output": "设计输出",
    "design_review": "设计评审",
    "design_verification": "设计验证",
    "design_validation": "设计确认",
    "design_change": "设计变更",
    "design_history_file": "设计历史文件(DHF)",
    "fmea_analysis": "FMEA分析报告",
    "risk_acceptance_criteria": "风险可接受准则",
    "periodic_risk_evaluation": "定期风险评价报告",
    "sop": "作业指导书(SOP)",
    "product_spec": "产品技术要求",
    "instruction": "使用说明书",
}

# ======================== 文档分类（9大生命周期阶段） ========================

DOC_CATEGORIES = {
    "design_planning": {
        "name": "一、设计策划",
        "description": "设计策划阶段 — 定义产品需求、风险管理计划、验证策略、注册路径",
        "icon": "📋",
        "types": [
            "design_development_plan", "product_requirements_spec", "risk_management_plan",
            "software_development_plan", "usability_engineering_plan", "biological_evaluation_plan",
            "sterilization_validation_plan", "packaging_validation_plan", "supplier_management_plan",
            "regulatory_strategy_document",
            "market_research_product_definition", "project_feasibility_study",
            "patent_analysis_report", "project_approval_review"
        ]
    },
    "design_input": {
        "name": "二、设计输入",
        "description": "设计输入阶段 — 功能、性能、安全、法规、使用环境等完整需求定义",
        "icon": "📥",
        "types": [
            "design_input", "software_requirements_spec", "hardware_requirements_spec",
            "ui_requirements_spec", "cybersecurity_requirements", "labeling_ifu_requirements",
            "user_needs_specification", "preliminary_risk_analysis", "product_risk_analysis_matrix",
            "cybersecurity_risk_analysis_matrix", "software_config_management_plan",
            "structural_design_requirements", "packaging_labeling_requirements",
            "product_rtm", "software_rtm", "cybersecurity_traceability_matrix",
            "essential_principles_checklist", "software_development_plan", "software_development_plan_di"
        ]
    },
    "design_output": {
        "name": "三、设计输出",
        "description": "设计输出阶段 — 图纸、BOM、软件架构、包装设计、IFU等",
        "icon": "📤",
        "types": [
            "product_drawings", "bill_of_materials", "product_specification",
            "software_architecture_doc", "software_detailed_design", "hardware_design_doc",
            "firmware_design_doc", "industrial_design_doc", "label_nameplate_artwork",
            "packaging_design_artwork", "instruction_for_use", "manufacturing_process_draft",
            "hardware_design_plan", "structural_design_plan", "software_coding_standard",
            "packaging_labeling_design_plan", "primary_packaging_material_report",
            "performance_research_records", "inspection_method_validation",
            "material_specification_drawing", "process_flow_diagram",
            "tooling_drawing_acceptance", "approved_supplier_list", "design_output_checklist"
        ]
    },
    "design_verification": {
        "name": "四、设计验证",
        "description": "设计验证阶段 — 电气安全、EMC、软件测试、输注精度、环境可靠性等39项验证",
        "icon": "🔬",
        "types": [
            "design_verification_master_plan", "electrical_safety_test_report",
            "emc_test_report", "alarm_system_test_report", "infusion_accuracy_test_report",
            "software_unit_test_report", "software_integration_test_report",
            "software_system_test_report", "battery_performance_test_report",
            "ip_rating_test_report", "environmental_reliability_test",
            "package_transport_test_report", "seal_integrity_test_report",
            "material_characterization_report", "accelerated_aging_test_report",
            "sensor_calibration_validation", "cybersecurity_test_report",
            "performance_verification_plan", "performance_verification_report",
            "software_unit_test_plan", "software_integration_test_plan",
            "software_system_test_plan", "software_quality_test_plan",
            "software_quality_test_report", "cybersecurity_test_plan",
            "software_interface_security_test_plan", "software_interface_security_test_report",
            "packaging_verification_plan", "packaging_verification_report",
            "service_life_verification_plan", "service_life_verification_report",
            "shelf_life_verification_plan", "shelf_life_verification_report",
            "transport_verification_plan", "leachables_test_plan",
            "leachables_test_report", "biocompatibility_drug_compatibility_report",
            "safety_emc_reliability_test_report", "registration_type_test_report"
        ]
    },
    "design_validation": {
        "name": "五、设计确认",
        "description": "设计确认阶段 — 可用性、临床评价、生物学评价、灭菌确认、过程确认",
        "icon": "✅",
        "types": [
            "design_validation_master_plan", "summative_usability_report",
            "clinical_evaluation_report", "biological_evaluation_report",
            "cytotoxicity_test_report", "skin_irritation_sensitization",
            "blood_compatibility_test_report", "sal_validation_report",
            "sterilization_residue_test_report", "process_validation_iq_oq_pq",
            "cleaning_validation_report",
            "clinical_trial_plan", "clinical_trial_report",
            "usability_test_plan", "usability_test_report",
            "design_validation_report"
        ]
    },
    "design_transfer": {
        "name": "六、设计转化",
        "description": "设计转化阶段 — 从研发到生产的交接，DMR、SOP、设备操作规程",
        "icon": "🏭",
        "types": [
            "design_transfer_plan", "design_transfer_report", "device_master_record",
            "manufacturing_sop", "inspection_sop", "equipment_operation_procedures",
            "work_environment_control_doc",
            "process_validation_plan", "sterilization_validation_protocol",
            "sterilization_validation_report", "process_validation_report"
        ]
    },
    "production": {
        "name": "七、生产制造",
        "description": "生产制造阶段 — 批记录、检验记录、DHR、不合格品处理、灭菌记录",
        "icon": "⚙️",
        "types": [
            "batch_production_record", "batch_inspection_record", "device_history_record",
            "incoming_inspection_records", "supplier_audit_reports", "calibration_records",
            "environmental_monitoring_records", "nonconforming_product_records",
            "sterilization_process_records", "udi_assignment_records"
        ]
    },
    "registration": {
        "name": "八、注册申报",
        "description": "注册申报阶段 — NMPA/FDA/CE技术文档、风险管理报告、符合性声明",
        "icon": "📝",
        "types": [
            "registration_dossier", "product_technical_requirements", "risk_management_report",
            "essential_safety_conformity", "software_version_description",
            "cybersecurity_disclosure", "clinical_evaluation_report_reg",
            "ifu_labeling_for_registration", "declaration_of_conformity", "qms_certificate_proof"
        ]
    },
    "post_market": {
        "name": "九、上市后",
        "description": "上市后阶段 — PMS、PMCF、投诉处理、不良事件、CAPA、内部审核",
        "icon": "📊",
        "types": [
            "pms_plan", "pmcf_plan", "complaint_handling_records", "adverse_event_reports",
            "periodic_safety_update_report", "capa_records", "change_control_records",
            "recall_field_safety_notice", "management_review_report", "internal_audit_reports",
            "pms_report"
        ]
    },
    "legacy": {
        "name": "通用/兼容",
        "description": "原有兼容类型 — 通用设计开发、风险管理、SOP等",
        "icon": "📄",
        "types": [
            "design_output", "design_review", "design_verification", "design_validation",
            "design_change", "design_history_file", "fmea_analysis", "risk_acceptance_criteria",
            "periodic_risk_evaluation", "sop", "product_spec", "instruction"
        ]
    }
}

# 基础上传格式（始终支持，使用本地解析器）
# 注意：.md 为纯文本，本地解析器可直接读取，始终支持，无需 MinerU
_BASE_UPLOAD_FORMATS = [".docx", ".pdf", ".txt", ".pptx", ".md"]

# MinerU 启用时可额外支持的格式
_MINERU_EXTRA_FORMATS = [".doc", ".ppt", ".xls", ".xlsx",
                         ".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif",
                         ".html", ".htm"]


def _compute_supported_upload_formats():
    """根据 MinerU 启用状态动态计算支持的上传格式列表

    注意：此处只检查 USE_MINERU 环境变量，不触发 SDK 导入。
    SDK 检测会在实际解析时延迟执行（mineru_service.is_mineru_sdk_available）。
    避免在模块加载阶段导入 mineru_vl_utils/transformers 等重依赖。
    """
    formats = list(_BASE_UPLOAD_FORMATS)
    try:
        from app.services.mineru_service import is_mineru_enabled
        if is_mineru_enabled():
            formats.extend(_MINERU_EXTRA_FORMATS)
    except Exception:
        pass
    # 去重保序
    seen = set()
    unique = []
    for ext in formats:
        if ext not in seen:
            seen.add(ext)
            unique.append(ext)
    return unique


SUPPORTED_UPLOAD_FORMATS = _compute_supported_upload_formats()
MAX_UPLOAD_SIZE_MB = 20
MAX_UPLOAD_SIZE_BYTES = MAX_UPLOAD_SIZE_MB * 1024 * 1024
