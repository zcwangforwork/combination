package com.insulinpump.usermgmt.dto;

import java.time.LocalDateTime;

/**
 * 文档修订历史 DTO（列表视图，不含 BLOB contentSnapshot）
 *
 * 用于 GET /api/documents/{id}/revisions 返回修订历史列表。
 * 如需下载某修订版本的文件内容，使用 /api/documents/revisions/{revId}/download。
 */
public class DocumentRevisionDto {

    private Long id;
    private Long documentId;
    private String version;
    private String title;
    private String fileName;
    private Long fileSize;
    private String changeLog;
    private Long publishedById;
    private String publishedByName;
    private LocalDateTime publishedAt;
    private LocalDateTime effectiveDate;
    private LocalDateTime obsoleteDate;
    private Long supersedesRevId;

    public DocumentRevisionDto() {}

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }

    public Long getDocumentId() { return documentId; }
    public void setDocumentId(Long documentId) { this.documentId = documentId; }

    public String getVersion() { return version; }
    public void setVersion(String version) { this.version = version; }

    public String getTitle() { return title; }
    public void setTitle(String title) { this.title = title; }

    public String getFileName() { return fileName; }
    public void setFileName(String fileName) { this.fileName = fileName; }

    public Long getFileSize() { return fileSize; }
    public void setFileSize(Long fileSize) { this.fileSize = fileSize; }

    public String getChangeLog() { return changeLog; }
    public void setChangeLog(String changeLog) { this.changeLog = changeLog; }

    public Long getPublishedById() { return publishedById; }
    public void setPublishedById(Long publishedById) { this.publishedById = publishedById; }

    public String getPublishedByName() { return publishedByName; }
    public void setPublishedByName(String publishedByName) { this.publishedByName = publishedByName; }

    public LocalDateTime getPublishedAt() { return publishedAt; }
    public void setPublishedAt(LocalDateTime publishedAt) { this.publishedAt = publishedAt; }

    public LocalDateTime getEffectiveDate() { return effectiveDate; }
    public void setEffectiveDate(LocalDateTime effectiveDate) { this.effectiveDate = effectiveDate; }

    public LocalDateTime getObsoleteDate() { return obsoleteDate; }
    public void setObsoleteDate(LocalDateTime obsoleteDate) { this.obsoleteDate = obsoleteDate; }

    public Long getSupersedesRevId() { return supersedesRevId; }
    public void setSupersedesRevId(Long supersedesRevId) { this.supersedesRevId = supersedesRevId; }
}
