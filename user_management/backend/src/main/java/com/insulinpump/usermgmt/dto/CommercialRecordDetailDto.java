package com.insulinpump.usermgmt.dto;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.LocalDateTime;

/**
 * 商业成本记录详情 DTO（含全量字段）
 */
public class CommercialRecordDetailDto {

    private Long id;
    private String itemName;
    private BigDecimal costPrice;
    private String currency;
    private LocalDate effectiveDate;
    private String confidentialityLevel;
    private String description;

    private Long supplierId;
    private String supplierCode;
    private String supplierName;

    private Long ownerId;
    private String ownerName;
    private String ownerDepartmentName;

    private Long optimisticLockVersion;
    private LocalDateTime createdAt;
    private LocalDateTime updatedAt;

    /** 当前用户对该记录的关系：owner=我的, admin=管理员 */
    private String accessRole;

    public CommercialRecordDetailDto() {}

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }

    public String getItemName() { return itemName; }
    public void setItemName(String itemName) { this.itemName = itemName; }

    public BigDecimal getCostPrice() { return costPrice; }
    public void setCostPrice(BigDecimal costPrice) { this.costPrice = costPrice; }

    public String getCurrency() { return currency; }
    public void setCurrency(String currency) { this.currency = currency; }

    public LocalDate getEffectiveDate() { return effectiveDate; }
    public void setEffectiveDate(LocalDate effectiveDate) { this.effectiveDate = effectiveDate; }

    public String getConfidentialityLevel() { return confidentialityLevel; }
    public void setConfidentialityLevel(String confidentialityLevel) { this.confidentialityLevel = confidentialityLevel; }

    public String getDescription() { return description; }
    public void setDescription(String description) { this.description = description; }

    public Long getSupplierId() { return supplierId; }
    public void setSupplierId(Long supplierId) { this.supplierId = supplierId; }

    public String getSupplierCode() { return supplierCode; }
    public void setSupplierCode(String supplierCode) { this.supplierCode = supplierCode; }

    public String getSupplierName() { return supplierName; }
    public void setSupplierName(String supplierName) { this.supplierName = supplierName; }

    public Long getOwnerId() { return ownerId; }
    public void setOwnerId(Long ownerId) { this.ownerId = ownerId; }

    public String getOwnerName() { return ownerName; }
    public void setOwnerName(String ownerName) { this.ownerName = ownerName; }

    public String getOwnerDepartmentName() { return ownerDepartmentName; }
    public void setOwnerDepartmentName(String ownerDepartmentName) { this.ownerDepartmentName = ownerDepartmentName; }

    public Long getOptimisticLockVersion() { return optimisticLockVersion; }
    public void setOptimisticLockVersion(Long optimisticLockVersion) { this.optimisticLockVersion = optimisticLockVersion; }

    public LocalDateTime getCreatedAt() { return createdAt; }
    public void setCreatedAt(LocalDateTime createdAt) { this.createdAt = createdAt; }

    public LocalDateTime getUpdatedAt() { return updatedAt; }
    public void setUpdatedAt(LocalDateTime updatedAt) { this.updatedAt = updatedAt; }

    public String getAccessRole() { return accessRole; }
    public void setAccessRole(String accessRole) { this.accessRole = accessRole; }
}
