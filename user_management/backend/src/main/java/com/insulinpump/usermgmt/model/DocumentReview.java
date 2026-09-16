package com.insulinpump.usermgmt.model;

import jakarta.persistence.*;
import java.time.LocalDateTime;

/**
 * 文档审批记录（不可变）
 *
 * 每次 approve / reject 时创建一条记录，构成文档的审批历史。
 * approve 时同时触发 publish 流程（创建 DocumentRevision 快照、版本号递增）。
 *
 * 关系图:
 *   t_document_review
 *      ├── document_id    -> t_document          (N:1, 仅存 id)
 *      └── reviewer_id    -> t_user              (N:1, 仅存 id)
 *
 * 字段说明:
 *   - decision        APPROVED=审批通过 / REJECTED=审批驳回
 *   - comment         审批意见（驳回时必填，通过时可选）
 *   - versionAfter    审批通过后的新版本号（仅 APPROVED 有值，REJECTED 为 null）
 *
 * 状态机对应关系:
 *   submitForReview: DRAFT -> REVIEW           （不创建 Review 记录）
 *   approve:         REVIEW -> PUBLISHED       （创建 Review{APPROVED, versionAfter=v1.0}）
 *   reject:          REVIEW -> DRAFT           （创建 Review{REJECTED, versionAfter=null}）
 */
@Entity
@Table(name = "t_document_review")
public class DocumentReview {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "document_id", nullable = false)
    private Long documentId;

    @Column(name = "reviewer_id", nullable = false)
    private Long reviewerId;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private ReviewDecision decision;

    @Column(length = 1000)
    private String comment;

    @Column(nullable = false, updatable = false)
    private LocalDateTime reviewedAt;

    /** 审批通过后的新版本号（仅 APPROVED 有值） */
    @Column(length = 20)
    private String versionAfter;

    @PrePersist
    protected void onCreate() {
        reviewedAt = LocalDateTime.now();
    }

    public DocumentReview() {}

    public DocumentReview(Long documentId, Long reviewerId, ReviewDecision decision,
                          String comment, String versionAfter) {
        this.documentId = documentId;
        this.reviewerId = reviewerId;
        this.decision = decision;
        this.comment = comment;
        this.versionAfter = versionAfter;
    }

    // ============ Getters and Setters ============

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }

    public Long getDocumentId() { return documentId; }
    public void setDocumentId(Long documentId) { this.documentId = documentId; }

    public Long getReviewerId() { return reviewerId; }
    public void setReviewerId(Long reviewerId) { this.reviewerId = reviewerId; }

    public ReviewDecision getDecision() { return decision; }
    public void setDecision(ReviewDecision decision) { this.decision = decision; }

    public String getComment() { return comment; }
    public void setComment(String comment) { this.comment = comment; }

    public LocalDateTime getReviewedAt() { return reviewedAt; }
    public void setReviewedAt(LocalDateTime reviewedAt) { this.reviewedAt = reviewedAt; }

    public String getVersionAfter() { return versionAfter; }
    public void setVersionAfter(String versionAfter) { this.versionAfter = versionAfter; }
}
