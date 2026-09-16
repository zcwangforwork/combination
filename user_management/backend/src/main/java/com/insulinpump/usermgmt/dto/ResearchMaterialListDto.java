package com.insulinpump.usermgmt.dto;

import java.time.LocalDateTime;

/**
 * 研发资料列表项 DTO
 *
 * 比体系文档多出 owner 字段，并标注当前用户对该资料的访问关系（owner/shared）
 */
public class ResearchMaterialListDto {

    private Long id;
    private String title;
    private String categoryName;
    private String fileName;
    private Long fileSize;
    private String fileType;
    private String fileExtension;
    private Long ownerId;
    private String ownerName;
    private String ownerDepartmentName;
    private LocalDateTime createdAt;

    // ============ 版本控制字段 ============
    private String version;
    private String status;

    /** 保密等级：PUBLIC/INTERNAL/CONFIDENTIAL/TOP_SECRET */
    private String confidentialityLevel;

    /** 当前用户对该资料的关系：owner=我的资料, shared=分享给我的 */
    private String accessRole;

    public ResearchMaterialListDto() {}

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }

    public String getTitle() { return title; }
    public void setTitle(String title) { this.title = title; }

    public String getCategoryName() { return categoryName; }
    public void setCategoryName(String categoryName) { this.categoryName = categoryName; }

    public String getFileName() { return fileName; }
    public void setFileName(String fileName) { this.fileName = fileName; }

    public Long getFileSize() { return fileSize; }
    public void setFileSize(Long fileSize) { this.fileSize = fileSize; }

    public String getFileType() { return fileType; }
    public void setFileType(String fileType) { this.fileType = fileType; }

    public String getFileExtension() { return fileExtension; }
    public void setFileExtension(String fileExtension) { this.fileExtension = fileExtension; }

    public Long getOwnerId() { return ownerId; }
    public void setOwnerId(Long ownerId) { this.ownerId = ownerId; }

    public String getOwnerName() { return ownerName; }
    public void setOwnerName(String ownerName) { this.ownerName = ownerName; }

    public String getOwnerDepartmentName() { return ownerDepartmentName; }
    public void setOwnerDepartmentName(String ownerDepartmentName) { this.ownerDepartmentName = ownerDepartmentName; }

    public LocalDateTime getCreatedAt() { return createdAt; }
    public void setCreatedAt(LocalDateTime createdAt) { this.createdAt = createdAt; }

    public String getVersion() { return version; }
    public void setVersion(String version) { this.version = version; }

    public String getStatus() { return status; }
    public void setStatus(String status) { this.status = status; }

    public String getConfidentialityLevel() { return confidentialityLevel; }
    public void setConfidentialityLevel(String confidentialityLevel) { this.confidentialityLevel = confidentialityLevel; }

    public String getAccessRole() { return accessRole; }
    public void setAccessRole(String accessRole) { this.accessRole = accessRole; }
}
