package com.insulinpump.usermgmt.model;

import jakarta.persistence.*;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

import java.time.LocalDateTime;
import java.util.Map;

/**
 * 文档元数据实体
 *
 * 与 DocumentFile 分表存储，列表查询仅访问本表，不加载 BLOB。
 *
 * doc_type 鉴别器：
 *   SYSTEM   - 体系文档（受控发布，组织拥有，owner=null）
 *   RESEARCH - 研发资料（个人私有+可分享，owner=上传人）
 *
 * 关系图：
 *   t_document
 *      ├── category_id    -> t_document_category (N:1)
 *      ├── uploader_id    -> t_user              (N:1, 上传操作人)
 *      ├── owner_id       -> t_user              (N:1, RESEARCH 时=上传人, SYSTEM 时=null)
 *      └── department_id  -> t_department        (N:1, 可空, 用于 DEPARTMENT 可见性)
 *
 *   t_document_file
 *      └── document_id    -> t_document          (1:1, 唯一)
 *
 *   t_document_share (仅 RESEARCH)
 *      └── document_id    -> t_document          (N:1, 级联删除)
 */
@Entity
@Table(name = "t_document")
public class Document {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    /**
     * 文档类型鉴别器：SYSTEM=体系文档, RESEARCH=研发资料
     * 决定可见性逻辑、上传权限、文件白名单
     */
    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private DocumentType docType = DocumentType.SYSTEM;

    @Column(nullable = false, length = 200)
    private String title;

    @Column(length = 1000)
    private String description;

    @Column(nullable = false, length = 255)
    private String fileName;

    @Column(nullable = false)
    private Long fileSize;

    @Column(nullable = false, length = 100)
    private String fileType;  // MIME type

    @Column(nullable = false, length = 20)
    private String fileExtension;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private DocumentVisibility visibility;

    /**
     * 保密等级（仅 RESEARCH 类型使用，SYSTEM 类型为 null）
     * 控制研发资料的可见性、分享、下载权限
     */
    @Enumerated(EnumType.STRING)
    @Column(length = 20)
    private ConfidentialityLevel confidentialityLevel;

    /**
     * 来源溯源（仅 RESEARCH 原理文档使用，III 类医疗器械合规）
     * 存储：{origin(FACTORY/THIRD_PARTY/COMMON), thirdPartyName, obtainedDate, agreementNo}
     * SYSTEM 文档与 RESEARCH 非原理文档为 null。
     */
    @JdbcTypeCode(SqlTypes.JSON)
    @Column(columnDefinition = "jsonb")
    private Map<String, Object> sourceProvenance;

    // ============ 版本控制字段 ============

    /** 文档版本号，如 v1.0、v1.1。DRAFT 时为 null，首次 publish 后设为 v1.0 */
    @Column(length = 20)
    private String version;

    /** 文档状态（DRAFT/REVIEW/PUBLISHED/OBSOLETE），默认 DRAFT */
    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private DocumentStatus status = DocumentStatus.DRAFT;

    /** 当前版本生效时间（publish 时设置） */
    private LocalDateTime effectiveDate;

    /** 作废时间（retire 时设置） */
    private LocalDateTime obsoleteDate;

    /**
     * JPA 乐观锁版本号，防止并发发布冲突。
     * 注意：与文档版本号(version)是不同概念，此字段由 JPA 自动管理。
     */
    @Version
    private Long optimisticLockVersion;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "category_id", nullable = false)
    private DocumentCategory category;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "uploader_id", nullable = false)
    private User uploader;

    /**
     * 研发资料的归属人（RESEARCH 时 = 上传人，SYSTEM 时 = null）
     * 用于 RESEARCH 可见性校验：owner + shared users 可见
     */
    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "owner_id")
    private User owner;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "department_id")
    private Department department;

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

    public Document() {}

    // Getters and Setters
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

    public DocumentVisibility getVisibility() { return visibility; }
    public void setVisibility(DocumentVisibility visibility) { this.visibility = visibility; }

    public ConfidentialityLevel getConfidentialityLevel() { return confidentialityLevel; }
    public void setConfidentialityLevel(ConfidentialityLevel confidentialityLevel) { this.confidentialityLevel = confidentialityLevel; }

    public Map<String, Object> getSourceProvenance() { return sourceProvenance; }
    public void setSourceProvenance(Map<String, Object> sourceProvenance) { this.sourceProvenance = sourceProvenance; }

    // ============ docType / owner Getters/Setters ============

    public DocumentType getDocType() { return docType; }
    public void setDocType(DocumentType docType) { this.docType = docType; }

    public User getOwner() { return owner; }
    public void setOwner(User owner) { this.owner = owner; }

    // ============ 版本控制 Getters/Setters ============

    public String getVersion() { return version; }
    public void setVersion(String version) { this.version = version; }

    public DocumentStatus getStatus() { return status; }
    public void setStatus(DocumentStatus status) { this.status = status; }

    public LocalDateTime getEffectiveDate() { return effectiveDate; }
    public void setEffectiveDate(LocalDateTime effectiveDate) { this.effectiveDate = effectiveDate; }

    public LocalDateTime getObsoleteDate() { return obsoleteDate; }
    public void setObsoleteDate(LocalDateTime obsoleteDate) { this.obsoleteDate = obsoleteDate; }

    public Long getOptimisticLockVersion() { return optimisticLockVersion; }
    public void setOptimisticLockVersion(Long optimisticLockVersion) { this.optimisticLockVersion = optimisticLockVersion; }

    public DocumentCategory getCategory() { return category; }
    public void setCategory(DocumentCategory category) { this.category = category; }

    public User getUploader() { return uploader; }
    public void setUploader(User uploader) { this.uploader = uploader; }

    public Department getDepartment() { return department; }
    public void setDepartment(Department department) { this.department = department; }

    public LocalDateTime getCreatedAt() { return createdAt; }
    public void setCreatedAt(LocalDateTime createdAt) { this.createdAt = createdAt; }

    public LocalDateTime getUpdatedAt() { return updatedAt; }
    public void setUpdatedAt(LocalDateTime updatedAt) { this.updatedAt = updatedAt; }
}
