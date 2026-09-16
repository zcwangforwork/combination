package com.insulinpump.usermgmt.model;

import jakarta.persistence.*;
import java.time.LocalDateTime;

/**
 * 文档文件 BLOB 实体（与 Document 元数据分表存储）
 *
 * 设计要点：
 * - 元数据与 BLOB 分表，避免列表查询时加载 BLOB
 * - document_id 唯一约束，1:1 关系
 * - checksum 用于完整性校验
 *
 * 关系图：
 *   t_document (1) ──────── (1) t_document_file
 *        id  <── document_id (FK, unique)
 */
@Entity
@Table(name = "t_document_file")
public class DocumentFile {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "document_id", nullable = false, unique = true)
    private Long documentId;

    @Lob
    @Column(nullable = false)
    private byte[] content;

    @Column(nullable = false, length = 64)
    private String checksum;

    @Column(nullable = false, updatable = false)
    private LocalDateTime createdAt;

    @PrePersist
    protected void onCreate() {
        createdAt = LocalDateTime.now();
    }

    public DocumentFile() {}

    public DocumentFile(Long documentId, byte[] content, String checksum) {
        this.documentId = documentId;
        this.content = content;
        this.checksum = checksum;
    }

    // Getters and Setters
    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }

    public Long getDocumentId() { return documentId; }
    public void setDocumentId(Long documentId) { this.documentId = documentId; }

    public byte[] getContent() { return content; }
    public void setContent(byte[] content) { this.content = content; }

    public String getChecksum() { return checksum; }
    public void setChecksum(String checksum) { this.checksum = checksum; }

    public LocalDateTime getCreatedAt() { return createdAt; }
    public void setCreatedAt(LocalDateTime createdAt) { this.createdAt = createdAt; }
}
