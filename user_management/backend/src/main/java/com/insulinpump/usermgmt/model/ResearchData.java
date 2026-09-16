package com.insulinpump.usermgmt.model;

import jakarta.persistence.*;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.Map;

/**
 * 研发数据实体（结构化记录，区别于 Document 的文件存储）
 *
 * 用于存储胰岛素泵研发过程中的测试记录、设计参数、实验记录、故障记录等结构化数据。
 * 用户通过前端表格直接录入，数据存入数据库（非文件上传）。
 *
 * 类型相关字段通过 extra_data (JSONB) 存储，按 recordType 区分模板：
 *   TEST_RECORD  - {testItem, testConditions, measuredResult, specification, passFail, testEquipment}
 *   DESIGN_PARAM - {paramName, paramValue, unit, specification, version, changeReason}
 *   EXPERIMENT   - {objective, method, parameters, observation, conclusion}
 *   FAILURE      - {phenomenon, rootCause, action, trackingNo, resolvedAt}
 *
 * 关系图：
 *   t_research_data
 *      ├── category_id  -> t_document_category (N:1, 可空, 复用 RESEARCH 分类)
 *      └── owner_id     -> t_user              (N:1, 录入人=所有者)
 *
 * 权限：owner + ADMIN 可编辑/删除；可见性受保密等级约束（复用 RESEARCH 资料逻辑）。
 */
@Entity
@Table(name = "t_research_data")
public class ResearchData {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    /** 记录类型 */
    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private ResearchDataType recordType;

    /** 记录编号，如 TEST-2026-001 */
    @Column(length = 50)
    private String recordNo;

    /** 标题/摘要 */
    @Column(nullable = false, length = 200)
    private String title;

    /** 记录日期 */
    private LocalDate recordDate;

    /** 操作员/执行人 */
    @Column(length = 50)
    private String operator;

    /** 状态 */
    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private ResearchDataStatus status = ResearchDataStatus.DRAFT;

    /** 设备型号，如 IP-2026-A */
    @Column(length = 50)
    private String deviceModel;

    /** 批次号 */
    @Column(length = 50)
    private String batchNo;

    /** 保密等级（默认 INTERNAL） */
    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private ConfidentialityLevel confidentialityLevel = ConfidentialityLevel.INTERNAL;

    /** 描述/备注 */
    @Column(length = 2000)
    private String description;

    /** 类型相关扩展字段（JSONB） */
    @JdbcTypeCode(SqlTypes.JSON)
    @Column(columnDefinition = "jsonb")
    private Map<String, Object> extraData;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "category_id")
    private DocumentCategory category;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "owner_id", nullable = false)
    private User owner;

    @Column(nullable = false, updatable = false)
    private LocalDateTime createdAt;

    private LocalDateTime updatedAt;

    @PrePersist
    protected void onCreate() {
        createdAt = LocalDateTime.now();
        updatedAt = LocalDateTime.now();
    }

    @PreUpdate
    protected void onUpdate() {
        updatedAt = LocalDateTime.now();
    }

    public ResearchData() {}

    // Getters and Setters
    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }

    public ResearchDataType getRecordType() { return recordType; }
    public void setRecordType(ResearchDataType recordType) { this.recordType = recordType; }

    public String getRecordNo() { return recordNo; }
    public void setRecordNo(String recordNo) { this.recordNo = recordNo; }

    public String getTitle() { return title; }
    public void setTitle(String title) { this.title = title; }

    public LocalDate getRecordDate() { return recordDate; }
    public void setRecordDate(LocalDate recordDate) { this.recordDate = recordDate; }

    public String getOperator() { return operator; }
    public void setOperator(String operator) { this.operator = operator; }

    public ResearchDataStatus getStatus() { return status; }
    public void setStatus(ResearchDataStatus status) { this.status = status; }

    public String getDeviceModel() { return deviceModel; }
    public void setDeviceModel(String deviceModel) { this.deviceModel = deviceModel; }

    public String getBatchNo() { return batchNo; }
    public void setBatchNo(String batchNo) { this.batchNo = batchNo; }

    public ConfidentialityLevel getConfidentialityLevel() { return confidentialityLevel; }
    public void setConfidentialityLevel(ConfidentialityLevel confidentialityLevel) { this.confidentialityLevel = confidentialityLevel; }

    public String getDescription() { return description; }
    public void setDescription(String description) { this.description = description; }

    public Map<String, Object> getExtraData() { return extraData; }
    public void setExtraData(Map<String, Object> extraData) { this.extraData = extraData; }

    public DocumentCategory getCategory() { return category; }
    public void setCategory(DocumentCategory category) { this.category = category; }

    public User getOwner() { return owner; }
    public void setOwner(User owner) { this.owner = owner; }

    public LocalDateTime getCreatedAt() { return createdAt; }
    public void setCreatedAt(LocalDateTime createdAt) { this.createdAt = createdAt; }

    public LocalDateTime getUpdatedAt() { return updatedAt; }
    public void setUpdatedAt(LocalDateTime updatedAt) { this.updatedAt = updatedAt; }
}
