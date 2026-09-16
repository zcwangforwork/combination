package com.insulinpump.usermgmt.dto;

import java.time.LocalDateTime;
import java.util.Map;

/**
 * 研发资料详情 DTO
 *
 * 比体系文档多出 owner 字段和 accessRole 标注
 */
public class ResearchMaterialDetailDto {

    private Long id;
    private String title;
    private String description;
    private String fileName;
    private Long fileSize;
    private String fileType;
    private String fileExtension;
    private Long categoryId;
    private String categoryName;
    private String categoryCode;
    private Long ownerId;
    private String ownerName;
    private String ownerDepartmentName;
    private String checksum;
    private LocalDateTime createdAt;
    private LocalDateTime updatedAt;

    // ============ 版本控制字段 ============
    private String version;
    private String status;
    private LocalDateTime effectiveDate;
    private LocalDateTime obsoleteDate;

    /** 保密等级：PUBLIC/INTERNAL/CONFIDENTIAL/TOP_SECRET */
    private String confidentialityLevel;

    /**
     * 来源溯源（仅 RESEARCH 原理文档有值，III 类医疗器械合规）
     * 字段：{origin(FACTORY/THIRD_PARTY/COMMON), thirdPartyName, obtainedDate, agreementNo}
     */
    private Map<String, Object> sourceProvenance;

    /** 当前用户对该资料的关系：owner=我的资料, shared=分享给我的, admin=管理员查看 */
    private String accessRole;

    public ResearchMaterialDetailDto() {}

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }

    public String getTitle() { return title; }
    public void setTitle(String title) { this.title = title; }

    public String getDescription() { return description; }
    public void setDescription(String description) { this.description = description; }

    public String getFileName() { return fileName; }
    public void setFileName(String fileName) { this.fileName = fileName; }

    public Long getFileSize() { return fileSize; }
    public void setFileSize(Long fileSize) { this.fileSize = fileSize; }

    public String getFileType() { return fileType; }
    public void setFileType(String fileType) { this.fileType = fileType; }

    public String getFileExtension() { return fileExtension; }
    public void setFileExtension(String fileExtension) { this.fileExtension = fileExtension; }

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

    public String getChecksum() { return checksum; }
    public void setChecksum(String checksum) { this.checksum = checksum; }

    public LocalDateTime getCreatedAt() { return createdAt; }
    public void setCreatedAt(LocalDateTime createdAt) { this.createdAt = createdAt; }

    public LocalDateTime getUpdatedAt() { return updatedAt; }
    public void setUpdatedAt(LocalDateTime updatedAt) { this.updatedAt = updatedAt; }

    public String getVersion() { return version; }
    public void setVersion(String version) { this.version = version; }

    public String getStatus() { return status; }
    public void setStatus(String status) { this.status = status; }

    public LocalDateTime getEffectiveDate() { return effectiveDate; }
    public void setEffectiveDate(LocalDateTime effectiveDate) { this.effectiveDate = effectiveDate; }

    public LocalDateTime getObsoleteDate() { return obsoleteDate; }
    public void setObsoleteDate(LocalDateTime obsoleteDate) { this.obsoleteDate = obsoleteDate; }

    public String getConfidentialityLevel() { return confidentialityLevel; }
    public void setConfidentialityLevel(String confidentialityLevel) { this.confidentialityLevel = confidentialityLevel; }

    public Map<String, Object> getSourceProvenance() { return sourceProvenance; }
    public void setSourceProvenance(Map<String, Object> sourceProvenance) { this.sourceProvenance = sourceProvenance; }

    public String getAccessRole() { return accessRole; }
    public void setAccessRole(String accessRole) { this.accessRole = accessRole; }
}
