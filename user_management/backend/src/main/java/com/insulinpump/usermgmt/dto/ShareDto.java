package com.insulinpump.usermgmt.dto;

import java.time.LocalDateTime;

/**
 * 分享记录 DTO（用于分享管理列表）
 */
public class ShareDto {

    private Long id;
    private Long documentId;
    private Long sharedWithUserId;
    private String sharedWithUserName;
    private String sharedWithUserDepartment;
    private Long sharedByUserId;
    private String sharedByUserName;
    private LocalDateTime createdAt;

    public ShareDto() {}

    public ShareDto(Long id, Long documentId,
                    Long sharedWithUserId, String sharedWithUserName, String sharedWithUserDepartment,
                    Long sharedByUserId, String sharedByUserName,
                    LocalDateTime createdAt) {
        this.id = id;
        this.documentId = documentId;
        this.sharedWithUserId = sharedWithUserId;
        this.sharedWithUserName = sharedWithUserName;
        this.sharedWithUserDepartment = sharedWithUserDepartment;
        this.sharedByUserId = sharedByUserId;
        this.sharedByUserName = sharedByUserName;
        this.createdAt = createdAt;
    }

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }

    public Long getDocumentId() { return documentId; }
    public void setDocumentId(Long documentId) { this.documentId = documentId; }

    public Long getSharedWithUserId() { return sharedWithUserId; }
    public void setSharedWithUserId(Long sharedWithUserId) { this.sharedWithUserId = sharedWithUserId; }

    public String getSharedWithUserName() { return sharedWithUserName; }
    public void setSharedWithUserName(String sharedWithUserName) { this.sharedWithUserName = sharedWithUserName; }

    public String getSharedWithUserDepartment() { return sharedWithUserDepartment; }
    public void setSharedWithUserDepartment(String sharedWithUserDepartment) { this.sharedWithUserDepartment = sharedWithUserDepartment; }

    public Long getSharedByUserId() { return sharedByUserId; }
    public void setSharedByUserId(Long sharedByUserId) { this.sharedByUserId = sharedByUserId; }

    public String getSharedByUserName() { return sharedByUserName; }
    public void setSharedByUserName(String sharedByUserName) { this.sharedByUserName = sharedByUserName; }

    public LocalDateTime getCreatedAt() { return createdAt; }
    public void setCreatedAt(LocalDateTime createdAt) { this.createdAt = createdAt; }
}
