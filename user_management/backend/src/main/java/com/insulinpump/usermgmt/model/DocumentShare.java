package com.insulinpump.usermgmt.model;

import jakarta.persistence.*;
import java.time.LocalDateTime;

/**
 * 文档分享关系实体（实现真正的"指定多人可见"）
 *
 * 用于 RESEARCH 类型文档：Owner 可将资料分享给指定同事。
 * SYSTEM 类型文档不使用此表（仍用 DocumentVisibility 枚举控制）。
 *
 * 关系图：
 *   t_document (1) ──< (N) t_document_share (N) >── (1) t_user
 *                        │                    │
 *                        shared_by_user_id ──> t_user (分享操作人)
 *
 * 约束：
 *   UNIQUE(document_id, shared_with_user_id) - 同一文档不重复分享给同一人
 *   ON DELETE CASCADE - 文档删除时自动清理分享记录
 */
@Entity
@Table(name = "t_document_share",
    uniqueConstraints = @UniqueConstraint(columnNames = {"document_id", "shared_with_user_id"}))
public class DocumentShare {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "document_id", nullable = false)
    private Long documentId;

    @Column(name = "shared_with_user_id", nullable = false)
    private Long sharedWithUserId;

    @Column(name = "shared_by_user_id", nullable = false)
    private Long sharedByUserId;

    @Column(nullable = false, updatable = false)
    private LocalDateTime createdAt;

    @PrePersist
    protected void onCreate() {
        createdAt = LocalDateTime.now();
    }

    public DocumentShare() {}

    public DocumentShare(Long documentId, Long sharedWithUserId, Long sharedByUserId) {
        this.documentId = documentId;
        this.sharedWithUserId = sharedWithUserId;
        this.sharedByUserId = sharedByUserId;
    }

    // Getters and Setters
    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }

    public Long getDocumentId() { return documentId; }
    public void setDocumentId(Long documentId) { this.documentId = documentId; }

    public Long getSharedWithUserId() { return sharedWithUserId; }
    public void setSharedWithUserId(Long sharedWithUserId) { this.sharedWithUserId = sharedWithUserId; }

    public Long getSharedByUserId() { return sharedByUserId; }
    public void setSharedByUserId(Long sharedByUserId) { this.sharedByUserId = sharedByUserId; }

    public LocalDateTime getCreatedAt() { return createdAt; }
    public void setCreatedAt(LocalDateTime createdAt) { this.createdAt = createdAt; }
}
