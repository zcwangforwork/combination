package com.insulinpump.usermgmt.model;

import jakarta.persistence.*;

import java.time.LocalDateTime;

/**
 * 供应商主数据实体
 *
 * 用于存储胰岛素泵研发/生产过程中的供应商信息。
 * 主数据风格：所有登录用户可见，仅 ADMIN 可增删改。
 * 软删除：enabled=false 不断 FK 引用（历史成本记录保留供应商名）。
 *
 * 关系图：
 *   t_supplier
 *      └── 被 t_commercial_record.supplier_id 引用（N:1）
 *
 * 医疗器械供应链规范字段：
 *   - supplierCode: 供应商编码（唯一，便于引用）
 *   - qualificationStatus: 合格状态（QUALIFIED/PENDING/SUSPENDED）
 *   - qualityContactName/Phone: 质量联系人（NMPA 法规要求）
 */
@Entity
@Table(name = "t_supplier",
    uniqueConstraints = @UniqueConstraint(columnNames = {"supplier_code"}))
public class Supplier {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    /** 供应商编码（唯一，如 SUP-001） */
    @Column(name = "supplier_code", nullable = false, length = 50)
    private String supplierCode;

    /** 供应商名称 */
    @Column(nullable = false, length = 200)
    private String name;

    /** 联系人 */
    @Column(length = 50)
    private String contact;

    /** 联系电话 */
    @Column(length = 30)
    private String phone;

    /** 邮箱 */
    @Column(length = 100)
    private String email;

    /** 供应商分类（如：原材料/零部件/外协加工/服务） */
    @Column(length = 50)
    private String category;

    /** 合格状态（默认 PENDING） */
    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private QualificationStatus qualificationStatus = QualificationStatus.PENDING;

    /** 质量联系人姓名（NMPA 法规要求） */
    @Column(name = "quality_contact_name", length = 50)
    private String qualityContactName;

    /** 质量联系人电话 */
    @Column(name = "quality_contact_phone", length = 30)
    private String qualityContactPhone;

    /** 是否启用（软删除标志，false=已停用） */
    @Column(nullable = false)
    private Boolean enabled = true;

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

    public Supplier() {}

    // Getters and Setters
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

    public QualificationStatus getQualificationStatus() { return qualificationStatus; }
    public void setQualificationStatus(QualificationStatus qualificationStatus) { this.qualificationStatus = qualificationStatus; }

    public String getQualityContactName() { return qualityContactName; }
    public void setQualityContactName(String qualityContactName) { this.qualityContactName = qualityContactName; }

    public String getQualityContactPhone() { return qualityContactPhone; }
    public void setQualityContactPhone(String qualityContactPhone) { this.qualityContactPhone = qualityContactPhone; }

    public Boolean getEnabled() { return enabled; }
    public void setEnabled(Boolean enabled) { this.enabled = enabled; }

    public Long getOptimisticLockVersion() { return optimisticLockVersion; }
    public void setOptimisticLockVersion(Long optimisticLockVersion) { this.optimisticLockVersion = optimisticLockVersion; }

    public LocalDateTime getCreatedAt() { return createdAt; }
    public void setCreatedAt(LocalDateTime createdAt) { this.createdAt = createdAt; }

    public LocalDateTime getUpdatedAt() { return updatedAt; }
    public void setUpdatedAt(LocalDateTime updatedAt) { this.updatedAt = updatedAt; }
}
