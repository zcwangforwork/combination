package com.insulinpump.usermgmt.dto;

import com.insulinpump.usermgmt.model.ReviewDecision;

import java.time.LocalDateTime;

/**
 * 文档审批记录 DTO
 */
public class ReviewRecordDto {

    private Long id;
    private Long documentId;
    private Long reviewerId;
    private String reviewerName;
    private ReviewDecision decision;
    private String comment;
    private LocalDateTime reviewedAt;
    private String versionAfter;

    public ReviewRecordDto() {}

    public ReviewRecordDto(Long id, Long documentId, Long reviewerId, String reviewerName,
                           ReviewDecision decision, String comment, LocalDateTime reviewedAt,
                           String versionAfter) {
        this.id = id;
        this.documentId = documentId;
        this.reviewerId = reviewerId;
        this.reviewerName = reviewerName;
        this.decision = decision;
        this.comment = comment;
        this.reviewedAt = reviewedAt;
        this.versionAfter = versionAfter;
    }

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }

    public Long getDocumentId() { return documentId; }
    public void setDocumentId(Long documentId) { this.documentId = documentId; }

    public Long getReviewerId() { return reviewerId; }
    public void setReviewerId(Long reviewerId) { this.reviewerId = reviewerId; }

    public String getReviewerName() { return reviewerName; }
    public void setReviewerName(String reviewerName) { this.reviewerName = reviewerName; }

    public ReviewDecision getDecision() { return decision; }
    public void setDecision(ReviewDecision decision) { this.decision = decision; }

    public String getComment() { return comment; }
    public void setComment(String comment) { this.comment = comment; }

    public LocalDateTime getReviewedAt() { return reviewedAt; }
    public void setReviewedAt(LocalDateTime reviewedAt) { this.reviewedAt = reviewedAt; }

    public String getVersionAfter() { return versionAfter; }
    public void setVersionAfter(String versionAfter) { this.versionAfter = versionAfter; }
}
