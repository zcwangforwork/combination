package com.insulinpump.usermgmt.dto;

import java.math.BigDecimal;
import java.time.LocalDate;

/**
 * 商业成本记录创建/更新请求 DTO
 *
 * 创建时必填：supplierId, itemName, costPrice, effectiveDate
 * 更新时：所有字段可选（部分更新，非 null 字段才更新）
 *
 * 保密等级默认 CONFIDENTIAL（在 Service 层补默认值，请求 DTO 不强制）。
 */
public class CommercialRecordRequest {

    private Long supplierId;
    private String itemName;
    private BigDecimal costPrice;
    private String currency;
    private LocalDate effectiveDate;
    private String confidentialityLevel;
    private String description;

    /** 更新时必传，用于乐观锁校验 */
    private Long optimisticLockVersion;

    public Long getSupplierId() { return supplierId; }
    public void setSupplierId(Long supplierId) { this.supplierId = supplierId; }

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

    public Long getOptimisticLockVersion() { return optimisticLockVersion; }
    public void setOptimisticLockVersion(Long optimisticLockVersion) { this.optimisticLockVersion = optimisticLockVersion; }
}
