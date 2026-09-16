package com.insulinpump.usermgmt.model;

import jakarta.persistence.*;
import java.time.LocalDateTime;

/**
 * 文档分类实体
 *
 * 体系文档 5 大分类：质量手册 / 程序文件 / 作业指导书 / 记录表单 / 外部文件
 * 研发资料 7 大分类：设计原理图 / 参数规格书 / 算法文档 / 测试数据 / 仿真文件 / 原型文件 / 技术调研报告
 *
 * doc_type 字段区分分类归属：SYSTEM 类目仅用于体系文档，RESEARCH 类目仅用于研发资料
 */
@Entity
@Table(name = "t_document_category")
public class DocumentCategory {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true, length = 50)
    private String code;

    @Column(nullable = false, length = 100)
    private String name;

    @Column(length = 500)
    private String description;

    @Column(name = "sort_order")
    private Integer sortOrder;

    /**
     * 分类归属类型：SYSTEM=体系文档分类, RESEARCH=研发资料分类
     * 上传时校验：RESEARCH 文档只能选 docType=RESEARCH 的分类
     */
    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private DocumentType docType = DocumentType.SYSTEM;

    @Column(nullable = false, updatable = false)
    private LocalDateTime createdAt;

    @PrePersist
    protected void onCreate() {
        createdAt = LocalDateTime.now();
    }

    public DocumentCategory() {}

    public DocumentCategory(String code, String name, String description, Integer sortOrder) {
        this.code = code;
        this.name = name;
        this.description = description;
        this.sortOrder = sortOrder;
    }

    public DocumentCategory(String code, String name, String description, Integer sortOrder, DocumentType docType) {
        this.code = code;
        this.name = name;
        this.description = description;
        this.sortOrder = sortOrder;
        this.docType = docType;
    }

    // Getters and Setters
    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }

    public String getCode() { return code; }
    public void setCode(String code) { this.code = code; }

    public String getName() { return name; }
    public void setName(String name) { this.name = name; }

    public String getDescription() { return description; }
    public void setDescription(String description) { this.description = description; }

    public Integer getSortOrder() { return sortOrder; }
    public void setSortOrder(Integer sortOrder) { this.sortOrder = sortOrder; }

    public DocumentType getDocType() { return docType; }
    public void setDocType(DocumentType docType) { this.docType = docType; }

    public LocalDateTime getCreatedAt() { return createdAt; }
    public void setCreatedAt(LocalDateTime createdAt) { this.createdAt = createdAt; }
}
