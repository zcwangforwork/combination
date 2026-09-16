package com.insulinpump.usermgmt.dto;

import java.time.LocalDateTime;

/**
 * 供应商列表项 DTO（轻量，主数据风格）
 *
 * 用于管理端列表展示：所有登录用户可见，仅 ADMIN 可增删改。
 */
public class SupplierListDto {

    private Long id;
    private String supplierCode;
    private String name;
    private String contact;
    private String phone;
    private String email;
    private String category;
    private String qualificationStatus;
    private String qualityContactName;
    private String qualityContactPhone;
    private Boolean enabled;
    private LocalDateTime createdAt;
    private LocalDateTime updatedAt;

    public SupplierListDto() {}

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }

    public String getSupplierCode() { return supplierCode; }
    public void setSupplierCode(String supplierCode) { this.supplierCode = supplierCode; }

    public String getName() { return name; }
    public void setName(String name) { this.name = name; }

    public String getContact() { return contact; }
    public void setContact(String contact) { this.contact = contact; }

    public String getPhone() { return phone; }
    public void setPhone(String phone) { this.phone = phone; }

    public String getEmail() { return email; }
    public void setEmail(String email) { this.email = email; }

    public String getCategory() { return category; }
    public void setCategory(String category) { this.category = category; }

    public String getQualificationStatus() { return qualificationStatus; }
    public void setQualificationStatus(String qualificationStatus) { this.qualificationStatus = qualificationStatus; }

    public String getQualityContactName() { return qualityContactName; }
    public void setQualityContactName(String qualityContactName) { this.qualityContactName = qualityContactName; }

    public String getQualityContactPhone() { return qualityContactPhone; }
    public void setQualityContactPhone(String qualityContactPhone) { this.qualityContactPhone = qualityContactPhone; }

    public Boolean getEnabled() { return enabled; }
    public void setEnabled(Boolean enabled) { this.enabled = enabled; }

    public LocalDateTime getCreatedAt() { return createdAt; }
    public void setCreatedAt(LocalDateTime createdAt) { this.createdAt = createdAt; }

    public LocalDateTime getUpdatedAt() { return updatedAt; }
    public void setUpdatedAt(LocalDateTime updatedAt) { this.updatedAt = updatedAt; }
}
