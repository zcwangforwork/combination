package com.insulinpump.usermgmt.dto;

import java.time.LocalDateTime;

/**
 * 文档列表项 DTO（不含 BLOB，用于列表查询）
 */
public class DocumentListDto {

    private Long id;
    private String title;
    private String categoryName;
    private String fileName;
    private Long fileSize;
    private String fileType;
    private String fileExtension;
    private String visibility;
    private String uploaderName;
    private String departmentName;
    private LocalDateTime createdAt;

    // ============ 版本控制字段 ============
    private String version;
    private String status;

    public DocumentListDto() {}

    public DocumentListDto(Long id, String title, String categoryName, String fileName,
                           Long fileSize, String fileType, String fileExtension,
                           String visibility, String uploaderName, String departmentName,
                           LocalDateTime createdAt, String version, String status) {
        this.id = id;
        this.title = title;
        this.categoryName = categoryName;
        this.fileName = fileName;
        this.fileSize = fileSize;
        this.fileType = fileType;
        this.fileExtension = fileExtension;
        this.visibility = visibility;
        this.uploaderName = uploaderName;
        this.departmentName = departmentName;
        this.createdAt = createdAt;
        this.version = version;
        this.status = status;
    }

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

    public String getVisibility() { return visibility; }
    public void setVisibility(String visibility) { this.visibility = visibility; }

    public String getUploaderName() { return uploaderName; }
    public void setUploaderName(String uploaderName) { this.uploaderName = uploaderName; }

    public String getDepartmentName() { return departmentName; }
    public void setDepartmentName(String departmentName) { this.departmentName = departmentName; }

    public LocalDateTime getCreatedAt() { return createdAt; }
    public void setCreatedAt(LocalDateTime createdAt) { this.createdAt = createdAt; }

    public String getVersion() { return version; }
    public void setVersion(String version) { this.version = version; }

    public String getStatus() { return status; }
    public void setStatus(String status) { this.status = status; }
}
