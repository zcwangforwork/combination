package com.insulinpump.usermgmt.model;

import jakarta.persistence.*;
import java.time.LocalDateTime;

/**
 * 文档修订历史快照（不可变）
 *
 * 每次 publish 时创建一条快照，记录当时的完整状态（含 BLOB 副本）。
 * 用于版本历史查询、版本对比、回滚。
 *
 * 关系图:
 *   t_document_revision
 *      ├── document_id        -> t_document              (N:1)
 *      ├── published_by        -> t_user                  (N:1, 仅存 id, 不做 FK 关联)
 *      └── supersedes_rev_id   -> t_document_revision     (self, N:1, 前一版本)
 *
 * 版本链示例:
 *   revId=1, documentId=42, version=v1.0, supersedesRevId=null
 *   revId=2, documentId=42, version=v1.1, supersedesRevId=1
 *   revId=3, documentId=42, version=v1.2, supersedesRevId=2
 *
 * 注意: contentSnapshot 是 publish 时从 DocumentFile.content 复制而来的完整副本,
 *       与 DocumentFile 解耦, 即使后续 DocumentFile 被修改, Revision 仍保持原始内容。
 */
@Entity
@Table(name = "t_document_revision")
public class DocumentRevision {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "document_id", nullable = false)
    private Long documentId;

    @Column(nullable = false, length = 20)
    private String version;

    // ============ 元数据快照 ============

    @Column(nullable = false, length = 200)
    private String title;

    @Column(length = 1000)
    private String description;

    @Column(nullable = false, length = 255)
    private String fileName;

    @Column(nullable = false)
    private Long fileSize;

    @Column(nullable = false, length = 100)
    private String fileType;

    @Column(nullable = false, length = 20)
    private String fileExtension;

    // ============ BLOB 快照 ============

    /**
     * 文件内容快照（复用 DocumentFile 的 @Lob 模式）。
     * 注意: 读取时必须在事务上下文中（PostgreSQL oid 类型限制）。
     */
    @Lob
    @Column(nullable = false)
    private byte[] contentSnapshot;

    @Column(nullable = false, length = 64)
    private String checksum;

    // ============ 发布信息 ============

    @Column(name = "published_by", nullable = false)
    private Long publishedById;

    @Column(nullable = false, updatable = false)
    private LocalDateTime publishedAt;

    /** 该版本生效时间（= publish 时的 now） */
    private LocalDateTime effectiveDate;

    /** 该版本作废时间（被新版本取代时设置） */
    private LocalDateTime obsoleteDate;

    /** 变更说明（publish 时由用户填写） */
    @Column(length = 500)
    private String changeLog;

    /** 前一版本修订 ID（版本链） */
    @Column(name = "supersedes_rev_id")
    private Long supersedesRevId;

    @PrePersist
    protected void onCreate() {
        publishedAt = LocalDateTime.now();
    }

    public DocumentRevision() {}

    public DocumentRevision(Long documentId, String version, String title, String description,
                            String fileName, Long fileSize, String fileType, String fileExtension,
                            byte[] contentSnapshot, String checksum, Long publishedById,
                            LocalDateTime effectiveDate, String changeLog, Long supersedesRevId) {
        this.documentId = documentId;
        this.version = version;
        this.title = title;
        this.description = description;
        this.fileName = fileName;
        this.fileSize = fileSize;
        this.fileType = fileType;
        this.fileExtension = fileExtension;
        this.contentSnapshot = contentSnapshot;
        this.checksum = checksum;
        this.publishedById = publishedById;
        this.effectiveDate = effectiveDate;
        this.changeLog = changeLog;
        this.supersedesRevId = supersedesRevId;
    }

    // ============ Getters and Setters ============

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }

    public Long getDocumentId() { return documentId; }
    public void setDocumentId(Long documentId) { this.documentId = documentId; }

    public String getVersion() { return version; }
    public void setVersion(String version) { this.version = version; }

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

    public byte[] getContentSnapshot() { return contentSnapshot; }
    public void setContentSnapshot(byte[] contentSnapshot) { this.contentSnapshot = contentSnapshot; }

    public String getChecksum() { return checksum; }
    public void setChecksum(String checksum) { this.checksum = checksum; }

    public Long getPublishedById() { return publishedById; }
    public void setPublishedById(Long publishedById) { this.publishedById = publishedById; }

    public LocalDateTime getPublishedAt() { return publishedAt; }
    public void setPublishedAt(LocalDateTime publishedAt) { this.publishedAt = publishedAt; }

    public LocalDateTime getEffectiveDate() { return effectiveDate; }
    public void setEffectiveDate(LocalDateTime effectiveDate) { this.effectiveDate = effectiveDate; }

    public LocalDateTime getObsoleteDate() { return obsoleteDate; }
    public void setObsoleteDate(LocalDateTime obsoleteDate) { this.obsoleteDate = obsoleteDate; }

    public String getChangeLog() { return changeLog; }
    public void setChangeLog(String changeLog) { this.changeLog = changeLog; }

    public Long getSupersedesRevId() { return supersedesRevId; }
    public void setSupersedesRevId(Long supersedesRevId) { this.supersedesRevId = supersedesRevId; }
}
