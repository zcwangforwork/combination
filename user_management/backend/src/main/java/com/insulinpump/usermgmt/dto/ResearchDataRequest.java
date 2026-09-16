package com.insulinpump.usermgmt.dto;

import java.time.LocalDate;
import java.util.Map;

/**
 * 研发数据创建/更新请求 DTO
 *
 * 创建时必填：recordType, title
 * 更新时：所有字段可选（部分更新，非 null 字段才更新）
 *
 * paramCategory 仅当 recordType=DESIGN_PARAM 时使用，可选值：
 *   FACTORY_MEASURED（工厂实测值）/ EXTERNAL_TECHNICAL（对外技术参数）/ COMMON（常规常见参数）
 * Service 层会将其注入 extraData.paramCategory，并对 DESIGN_PARAM 类型校验非空。
 */
public class ResearchDataRequest {

    /** 记录类型：TEST_RECORD/DESIGN_PARAM/EXPERIMENT/FAILURE/OTHER */
    private String recordType;

    /**
     * 参数子分类（仅 DESIGN_PARAM 类型使用，Service 层注入 extraData.paramCategory）
     * 取值：FACTORY_MEASURED / EXTERNAL_TECHNICAL / COMMON
     */
    private String paramCategory;

    private String recordNo;
    private String title;
    private LocalDate recordDate;
    private String operator;
    private String status;
    private String deviceModel;
    private String batchNo;
    private String confidentialityLevel;
    private Long categoryId;
    private String description;
    private Map<String, Object> extraData;

    public String getRecordType() { return recordType; }
    public void setRecordType(String recordType) { this.recordType = recordType; }

    public String getParamCategory() { return paramCategory; }
    public void setParamCategory(String paramCategory) { this.paramCategory = paramCategory; }

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

    public Long getCategoryId() { return categoryId; }
    public void setCategoryId(Long categoryId) { this.categoryId = categoryId; }

    public String getDescription() { return description; }
    public void setDescription(String description) { this.description = description; }

    public Map<String, Object> getExtraData() { return extraData; }
    public void setExtraData(Map<String, Object> extraData) { this.extraData = extraData; }
}
