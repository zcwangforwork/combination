package com.insulinpump.usermgmt.dto;

/**
 * 供应商创建/更新请求 DTO
 *
 * 创建时必填：supplierCode, name
 * 更新时：所有字段可选（部分更新，非 null 字段才更新）
 *
 * 仅 ADMIN 角色可调用（见 SupplierController @PreAuthorize）
 */
public class SupplierRequest {

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

    /** 更新时必传，用于乐观锁校验 */
    private Long optimisticLockVersion;

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

    public Long getOptimisticLockVersion() { return optimisticLockVersion; }
    public void setOptimisticLockVersion(Long optimisticLockVersion) { this.optimisticLockVersion = optimisticLockVersion; }
}
