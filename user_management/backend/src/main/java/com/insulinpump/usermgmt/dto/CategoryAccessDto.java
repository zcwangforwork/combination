package com.insulinpump.usermgmt.dto;

import java.time.LocalDateTime;

/**
 * 资料分类授权响应 DTO
 *
 * 返回某用户的资料分类授权记录详情。
 */
public class CategoryAccessDto {

    private Long id;
    private Long userId;
    private String userName;
    private Long categoryId;
    private String categoryName;
    private String categoryCode;
    private String accessMode;
    private Long grantedById;
    private String grantedByName;
    private LocalDateTime grantedAt;

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }

    public Long getUserId() { return userId; }
    public void setUserId(Long userId) { this.userId = userId; }

    public String getUserName() { return userName; }
    public void setUserName(String userName) { this.userName = userName; }

    public Long getCategoryId() { return categoryId; }
    public void setCategoryId(Long categoryId) { this.categoryId = categoryId; }

    public String getCategoryName() { return categoryName; }
    public void setCategoryName(String categoryName) { this.categoryName = categoryName; }

    public String getCategoryCode() { return categoryCode; }
    public void setCategoryCode(String categoryCode) { this.categoryCode = categoryCode; }

    public String getAccessMode() { return accessMode; }
    public void setAccessMode(String accessMode) { this.accessMode = accessMode; }

    public Long getGrantedById() { return grantedById; }
    public void setGrantedById(Long grantedById) { this.grantedById = grantedById; }

    public String getGrantedByName() { return grantedByName; }
    public void setGrantedByName(String grantedByName) { this.grantedByName = grantedByName; }

    public LocalDateTime getGrantedAt() { return grantedAt; }
    public void setGrantedAt(LocalDateTime grantedAt) { this.grantedAt = grantedAt; }
}
