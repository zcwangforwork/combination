package com.insulinpump.usermgmt.model;

import jakarta.persistence.*;
import java.time.LocalDateTime;

/**
 * 用户资料分类授权实体
 *
 * 用于管理员给任意员工分配"可访问某 RESEARCH 资料分类"权限（用户级，独立于角色）。
 * 一条记录表示某用户被授权访问某 RESEARCH 分类下的资料。
 *
 * 与 UserConfidentialityAccess 互补：
 *   - UserConfidentialityAccess: 按保密等级授权（PUBLIC/INTERNAL/CONFIDENTIAL/TOP_SECRET）
 *   - UserCategoryAccess:        按资料分类授权（仅 RESEARCH 分类，如 FACTORY_PROCESS / TEST_DATA 等）
 *
 * 组合规则（DataVisibilityChecker.canAccess 5-arg）：与 allowedLevels OR 组合。
 *   任一命中即可见。但 TOP_SECRET 必须由 allowedLevels=TOP_SECRET 单独释放，
 *   categoryAccess 仅释放非 TOP_SECRET 资料。
 *
 * 表关系：
 *   t_user_category_access
 *      ├── user_id        -> t_user (N:1, 被授权人)
 *      ├── category_id    -> t_document_category (N:1, RESEARCH 分类)
 *      └── granted_by     -> t_user (N:1, 授权操作人，可空)
 *
 * 审计字段：granted_by + granted_at 满足医疗器械合规要求。
 *
 * 删除级联：DB 层 ON DELETE CASCADE（删 User 时自动清理授权记录）。
 */
@Entity
@Table(name = "t_user_category_access",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_user_cat_access_user_category",
        columnNames = {"user_id", "category_id"}))
public class UserCategoryAccess {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    /** 被授权用户 */
    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "user_id", nullable = false,
        foreignKey = @ForeignKey(name = "fk_user_cat_access_user"))
    private User user;

    /**
     * 被授权的资料分类（仅 RESEARCH 分类，SYSTEM 分类在 Controller 层拒绝）。
     * EAGER 加载：JwtAuthFilter 一次性加载所有授权分类，避免 N+1。
     */
    @ManyToOne(fetch = FetchType.EAGER, optional = false)
    @JoinColumn(name = "category_id", nullable = false,
        foreignKey = @ForeignKey(name = "fk_user_cat_access_category"))
    private DocumentCategory category;

    /** 授权操作人（ADMIN），可空以兼容历史数据 */
    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "granted_by",
        foreignKey = @ForeignKey(name = "fk_user_cat_access_granted_by"))
    private User grantedBy;

    /**
     * 授权访问模式：READ_ONLY（只读）/ READ_WRITE（可读写）
     * 历史记录为 NULL 时按 READ_ONLY 处理。
     */
    @Enumerated(EnumType.STRING)
    @Column(name = "access_mode", length = 20)
    private AccessMode accessMode = AccessMode.READ_ONLY;

    /** 授权时间 */
    @Column(nullable = false)
    private LocalDateTime grantedAt;

    @PrePersist
    protected void onCreate() {
        grantedAt = LocalDateTime.now();
    }

    public UserCategoryAccess() {}

    public UserCategoryAccess(User user, DocumentCategory category, User grantedBy) {
        this.user = user;
        this.category = category;
        this.grantedBy = grantedBy;
    }

    public UserCategoryAccess(User user, DocumentCategory category, User grantedBy,
                              AccessMode accessMode) {
        this(user, category, grantedBy);
        this.accessMode = accessMode;
    }

    // Getters and Setters
    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }

    public User getUser() { return user; }
    public void setUser(User user) { this.user = user; }

    public DocumentCategory getCategory() { return category; }
    public void setCategory(DocumentCategory category) { this.category = category; }

    public User getGrantedBy() { return grantedBy; }
    public void setGrantedBy(User grantedBy) { this.grantedBy = grantedBy; }

    public AccessMode getAccessMode() { return accessMode; }
    public void setAccessMode(AccessMode accessMode) { this.accessMode = accessMode; }

    public LocalDateTime getGrantedAt() { return grantedAt; }
    public void setGrantedAt(LocalDateTime grantedAt) { this.grantedAt = grantedAt; }
}
