package com.insulinpump.usermgmt.model;

import jakarta.persistence.*;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.LocalDateTime;

/**
 * 商业成本记录实体（独立于 ResearchData，因需非空 supplier FK + BigDecimal 精度）
 *
 * 用于存储胰岛素泵零部件/原材料的成本价格记录。
 * 可见性规则（同 ResearchData）：
 *   - owner       : 看自己录入的所有等级记录
 *   - ADMIN       : 看全部记录
 *   - 其他登录用户 : 只看 PUBLIC 等级记录
 *
 * 保密等级默认 CONFIDENTIAL（成本价是敏感商业数据）。
 *
 * 关系图：
 *   t_commercial_record
 *      ├── supplier_id -> t_supplier   (N:1, 非空 FK)
 *      └── owner_id    -> t_user       (N:1, 录入人)
 */
@Entity
@Table(name = "t_commercial_record")
public class CommercialRecord {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    /** 供应商（非空 FK） */
    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "supplier_id", nullable = false)
    private Supplier supplier;

    /** 物料/项目名称 */
    @Column(nullable = false, length = 200)
    private String itemName;

    /** 成本价（精度 scale=2，如 12.50） */
    @Column(nullable = false, precision = 12, scale = 2)
    private BigDecimal costPrice;

    /** 货币（默认 CNY） */
    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 10)
    private Currency currency = Currency.CNY;

    /** 生效日期 */
    @Column(nullable = false)
    private LocalDate effectiveDate;

    /** 保密等级（默认 CONFIDENTIAL - 成本价是敏感数据） */
    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private ConfidentialityLevel confidentialityLevel = ConfidentialityLevel.CONFIDENTIAL;

    /** 描述/备注 */
    @Column(length = 1000)
    private String description;

    /** 录入人（owner） */
    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "owner_id", nullable = false)
    private User owner;

    /**
     * JPA 乐观锁版本号，防止并发编辑冲突。
     */
    @Version
    private Long optimisticLockVersion;

    @Column(nullable = false, updatable = false)
    private LocalDateTime createdAt;

    private LocalDateTime updatedAt;

    @PrePersist
    protected void onCreate() {
        createdAt = LocalDateTime.now();
        updatedAt = LocalDateTime.now();
    }

    @PreUpdate
    protected void onUpdate() {
        updatedAt = LocalDateTime.now();
    }

    public CommercialRecord() {}

    // Getters and Setters
    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }

    public Supplier getSupplier() { return supplier; }
    public void setSupplier(Supplier supplier) { this.supplier = supplier; }

    public String getItemName() { return itemName; }
    public void setItemName(String itemName) { this.itemName = itemName; }

    public BigDecimal getCostPrice() { return costPrice; }
    public void setCostPrice(BigDecimal costPrice) { this.costPrice = costPrice; }

    public Currency getCurrency() { return currency; }
    public void setCurrency(Currency currency) { this.currency = currency; }

    public LocalDate getEffectiveDate() { return effectiveDate; }
    public void setEffectiveDate(LocalDate effectiveDate) { this.effectiveDate = effectiveDate; }

    public ConfidentialityLevel getConfidentialityLevel() { return confidentialityLevel; }
    public void setConfidentialityLevel(ConfidentialityLevel confidentialityLevel) { this.confidentialityLevel = confidentialityLevel; }

    public String getDescription() { return description; }
    public void setDescription(String description) { this.description = description; }

    public User getOwner() { return owner; }
    public void setOwner(User owner) { this.owner = owner; }

    public Long getOptimisticLockVersion() { return optimisticLockVersion; }
    public void setOptimisticLockVersion(Long optimisticLockVersion) { this.optimisticLockVersion = optimisticLockVersion; }

    public LocalDateTime getCreatedAt() { return createdAt; }
    public void setCreatedAt(LocalDateTime createdAt) { this.createdAt = createdAt; }

    public LocalDateTime getUpdatedAt() { return updatedAt; }
    public void setUpdatedAt(LocalDateTime updatedAt) { this.updatedAt = updatedAt; }
}
