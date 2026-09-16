package com.insulinpump.usermgmt.dto;

import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.Map;

/**
 * 研发数据详情 DTO（含 extraData 全量字段）
 */
public class ResearchDataDetailDto {

    private Long id;
    private String recordType;
    private String recordNo;
    private String title;
    private LocalDate recordDate;
    private String operator;
    private String status;
    private String deviceModel;
    private String batchNo;
    private String confidentialityLevel;
    private String description;

    /** 参数子分类（仅 DESIGN_PARAM 类型有值，从 extraData.paramCategory 提取） */
    private String paramCategory;

    private Map<String, Object> extraData;

    private Long categoryId;
    private String categoryName;
    private String categoryCode;

    private Long ownerId;
    private String ownerName;
    private String ownerDepartmentName;

    private LocalDateTime createdAt;
    private LocalDateTime updatedAt;

    /** 当前用户对该记录的关系：owner=我的, admin=管理员 */
    private String accessRole;

    public ResearchDataDetailDto() {}

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }

    public String getRecordType() { return recordType; }
    public void setRecordType(String recordType) { this.recordType = recordType; }

    public String getRecordNo() { return recordNo; }
    public void setRecordNo(String recordNo) { this.recordNo = recordNo; }

    public String getTitle() { return title; }
    public void setTitle(String title) { this.title = title; }

    public LocalDate getRecordDate() { return recordDate; }
    public void setRecordDate(LocalDate recordDate) { this.recordDate = recordDate; }

    public String getOperator() { return operator; }
    public void setOperator(String operator) { this.operator = operator; }

    public String getStatus() { return status; }
    public void setStatus(String status) { this.status = status; }

    public String getDeviceModel() { return deviceModel; }
    public void setDeviceModel(String deviceModel) { this.deviceModel = deviceModel; }

    public String getBatchNo() { return batchNo; }
    public void setBatchNo(String batchNo) { this.batchNo = batchNo; }

    public String getConfidentialityLevel() { return confidentialityLevel; }
    public void setConfidentialityLevel(String confidentialityLevel) { this.confidentialityLevel = confidentialityLevel; }

    public String getDescription() { return description; }
    public void setDescription(String description) { this.description = description; }

    public String getParamCategory() { return paramCategory; }
    public void setParamCategory(String paramCategory) { this.paramCategory = paramCategory; }

    public Map<String, Object> getExtraData() { return extraData; }
    public void setExtraData(Map<String, Object> extraData) { this.extraData = extraData; }

    public Long getCategoryId() { return categoryId; }
    public void setCategoryId(Long categoryId) { this.categoryId = categoryId; }

    public String getCategoryName() { return categoryName; }
    public void setCategoryName(String categoryName) { this.categoryName = categoryName; }

    public String getCategoryCode() { return categoryCode; }
    public void setCategoryCode(String categoryCode) { this.categoryCode = categoryCode; }

    public Long getOwnerId() { return ownerId; }
    public void setOwnerId(Long ownerId) { this.ownerId = ownerId; }

    public String getOwnerName() { return ownerName; }
    public void setOwnerName(String ownerName) { this.ownerName = ownerName; }

    public String getOwnerDepartmentName() { return ownerDepartmentName; }
    public void setOwnerDepartmentName(String ownerDepartmentName) { this.ownerDepartmentName = ownerDepartmentName; }

    public LocalDateTime getCreatedAt() { return createdAt; }
    public void setCreatedAt(LocalDateTime createdAt) { this.createdAt = createdAt; }

    public LocalDateTime getUpdatedAt() { return updatedAt; }
    public void setUpdatedAt(LocalDateTime updatedAt) { this.updatedAt = updatedAt; }

    public String getAccessRole() { return accessRole; }
    public void setAccessRole(String accessRole) { this.accessRole = accessRole; }
}
