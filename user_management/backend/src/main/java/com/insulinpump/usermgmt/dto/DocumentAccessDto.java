package com.insulinpump.usermgmt.dto;

import java.time.LocalDateTime;

/**
 * 按资料授权响应 DTO
 *
 * 返回某用户被授权查看的具体研发资料清单。
 */
public class DocumentAccessDto {

    private Long documentId;
    private String documentTitle;
    private Long categoryId;
    private String categoryName;
    private String categoryCode;
    private String confidentialityLevel;
    private Long grantedByUserId;
    private String grantedByName;
    private LocalDateTime grantedAt;

    public Long getDocumentId() { return documentId; }
    public void setDocumentId(Long documentId) { this.documentId = documentId; }

    public String getDocumentTitle() { return documentTitle; }
    public void setDocumentTitle(String documentTitle) { this.documentTitle = documentTitle; }

    public Long getCategoryId() { return categoryId; }
    public void setCategoryId(Long categoryId) { this.categoryId = categoryId; }

    public String getCategoryName() { return categoryName; }
    public void setCategoryName(String categoryName) { this.categoryName = categoryName; }

    public String getCategoryCode() { return categoryCode; }
    public void setCategoryCode(String categoryCode) { this.categoryCode = categoryCode; }

    public String getConfidentialityLevel() { return confidentialityLevel; }
    public void setConfidentialityLevel(String confidentialityLevel) { this.confidentialityLevel = confidentialityLevel; }

    public Long getGrantedByUserId() { return grantedByUserId; }
    public void setGrantedByUserId(Long grantedByUserId) { this.grantedByUserId = grantedByUserId; }

    public String getGrantedByName() { return grantedByName; }
    public void setGrantedByName(String grantedByName) { this.grantedByName = grantedByName; }

    public LocalDateTime getGrantedAt() { return grantedAt; }
    public void setGrantedAt(LocalDateTime grantedAt) { this.grantedAt = grantedAt; }
}
