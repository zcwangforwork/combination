package com.insulinpump.usermgmt.dto;

import java.time.LocalDate;
import java.time.LocalDateTime;

/**
 * 研发数据列表项 DTO（轻量，不含 extraData/description）
 */
public class ResearchDataListDto {

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

    /** 参数子分类（仅 DESIGN_PARAM 类型有值，从 extraData.paramCategory 提取） */
    private String paramCategory;

    private Long categoryId;
    private String categoryName;
    private Long ownerId;
    private String ownerName;
    private String ownerDepartmentName;
    private LocalDateTime createdAt;

    /** 当前用户对该记录的关系：owner=我的, admin=管理员 */
    private String accessRole;

    public ResearchDataListDto() {}

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

    public String getParamCategory() { return paramCategory; }
    public void setParamCategory(String paramCategory) { this.paramCategory = paramCategory; }

    public Long getCategoryId() { return categoryId; }
    public void setCategoryId(Long categoryId) { this.categoryId = categoryId; }

    public String getCategoryName() { return categoryName; }
    public void setCategoryName(String categoryName) { this.categoryName = categoryName; }

    public Long getOwnerId() { return ownerId; }
    public void setOwnerId(Long ownerId) { this.ownerId = ownerId; }

    public String getOwnerName() { return ownerName; }
    public void setOwnerName(String ownerName) { this.ownerName = ownerName; }

    public String getOwnerDepartmentName() { return ownerDepartmentName; }
    public void setOwnerDepartmentName(String ownerDepartmentName) { this.ownerDepartmentName = ownerDepartmentName; }

    public LocalDateTime getCreatedAt() { return createdAt; }
    public void setCreatedAt(LocalDateTime createdAt) { this.createdAt = createdAt; }

    public String getAccessRole() { return accessRole; }
    public void setAccessRole(String accessRole) { this.accessRole = accessRole; }
}
