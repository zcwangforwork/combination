package com.insulinpump.usermgmt.model;

import jakarta.persistence.*;
import java.time.LocalDateTime;

/**
 * 用户保密等级授权实体
 *
 * 用于管理员给任意员工分配"可访问保密等级"权限（用户级，独立于角色）。
 * 一条记录表示某用户被授权访问某保密等级。
 *
 * 表关系：
 *   t_user_confidentiality_access
 *      ├── user_id        -> t_user (N:1, 被授权人)
 *      └── granted_by     -> t_user (N:1, 授权操作人，可空)
 *
 * 审计字段：granted_by + granted_at 满足医疗器械合规要求。
 *
 * 删除级联：DB 层 ON DELETE CASCADE（删 User 时自动清理授权记录），
 *          业务层 EmployeeService.deleteEmployee 不需要显式清理。
 */
@Entity
@Table(name = "t_user_confidentiality_access",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_user_conf_access_user_level",
        columnNames = {"user_id", "confidentiality_level"}))
public class UserConfidentialityAccess {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    /** 被授权用户 */
    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "user_id", nullable = false,
        foreignKey = @ForeignKey(name = "fk_user_conf_access_user"))
    private User user;

    /** 被授权的保密等级 */
    @Enumerated(EnumType.STRING)
    @Column(name = "confidentiality_level", nullable = false, length = 20)
    private ConfidentialityLevel confidentialityLevel;

    /** 授权操作人（ADMIN），可空以兼容历史数据 */
    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "granted_by",
        foreignKey = @ForeignKey(name = "fk_user_conf_access_granted_by"))
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

    public UserConfidentialityAccess() {}

    public UserConfidentialityAccess(User user, ConfidentialityLevel level, User grantedBy) {
        this.user = user;
        this.confidentialityLevel = level;
        this.grantedBy = grantedBy;
    }

    public UserConfidentialityAccess(User user, ConfidentialityLevel level, User grantedBy,
                                     AccessMode accessMode) {
        this(user, level, grantedBy);
        this.accessMode = accessMode;
    }

    // Getters and Setters
    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }

    public User getUser() { return user; }
    public void setUser(User user) { this.user = user; }

    public ConfidentialityLevel getConfidentialityLevel() { return confidentialityLevel; }
    public void setConfidentialityLevel(ConfidentialityLevel confidentialityLevel) {
        this.confidentialityLevel = confidentialityLevel;
    }

    public User getGrantedBy() { return grantedBy; }
    public void setGrantedBy(User grantedBy) { this.grantedBy = grantedBy; }

    public AccessMode getAccessMode() { return accessMode; }
    public void setAccessMode(AccessMode accessMode) { this.accessMode = accessMode; }

    public LocalDateTime getGrantedAt() { return grantedAt; }
    public void setGrantedAt(LocalDateTime grantedAt) { this.grantedAt = grantedAt; }
}
