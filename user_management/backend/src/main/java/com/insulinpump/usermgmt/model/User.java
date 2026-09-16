package com.insulinpump.usermgmt.model;

import com.fasterxml.jackson.annotation.JsonIgnore;
import jakarta.persistence.*;
import java.time.LocalDateTime;
import java.util.HashSet;
import java.util.Set;

@Entity
@Table(name = "t_user")
public class User {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true, length = 50)
    private String username;

    @Column(nullable = false)
    private String password;

    @Column(nullable = false, length = 50)
    private String realName;

    @Column(unique = true, length = 20)
    private String employeeNo;

    @Column(length = 100)
    private String email;

    @Column(length = 20)
    private String phone;

    @ManyToOne(fetch = FetchType.EAGER)
    @JoinColumn(name = "role_id", nullable = false)
    private Role role;

    @ManyToOne(fetch = FetchType.EAGER)
    @JoinColumn(name = "department_id")
    private Department department;

    /**
     * 用户级保密等级授权集（EAGER 加载，JwtAuthFilter 一次查全）。
     *
     * 含义：用户被授权访问的跨部门数据保密等级。
     *   - 自己录入的数据：不受此集合限制（owner 全见）
     *   - ADMIN：不受此集合限制（isAdmin 全见）
     *   - 同部门员工：本部门数据不受此集合限制（同部门全见）
     *   - 跨部门访问：必须命中此集合（allowedLevels 授权）
     *
     * 默认空集：普通员工可见自己 + 本部门他人数据，跨部门需显式授权。
     * 删除级联：DB 层 ON DELETE CASCADE 自动清理（开发计划 GAP #6）。
     */
    // @JsonIgnore：切断 User <-> 授权实体双向引用的 JSON 序列化循环（避免 StackOverflowError）
    // 授权信息通过各授权 Controller 的 DTO 返回，无需随 User 实体输出。
    @JsonIgnore
    @OneToMany(mappedBy = "user", fetch = FetchType.EAGER,
        cascade = CascadeType.ALL, orphanRemoval = true)
    private Set<UserConfidentialityAccess> confidentialityAccesses = new HashSet<>();

    /**
     * 用户级资料分类授权集（EAGER 加载，JwtAuthFilter 一次查全）。
     *
     * 含义：用户被授权访问的 RESEARCH 资料分类（跨部门场景）。
     *   - 自己录入的数据：不受此集合限制（owner 全见）
     *   - ADMIN：不受此集合限制（isAdmin 全见）
     *   - 同部门员工：本部门数据不受此集合限制（同部门全见）
     *   - 跨部门访问：allowedLevels 或 categoryAccesses 任一命中即可见（OR 组合）
     *
     * TOP_SECRET 隔离：categoryAccesses 仅释放非 TOP_SECRET 资料；
     *   TOP_SECRET 必须由 allowedLevels=TOP_SECRET 单独释放。
     *
     * 默认空集：普通员工可见自己 + 本部门他人数据，跨部门需显式授权。
     * 删除级联：DB 层 ON DELETE CASCADE 自动清理。
     */
    @JsonIgnore
    @OneToMany(mappedBy = "user", fetch = FetchType.EAGER,
        cascade = CascadeType.ALL, orphanRemoval = true)
    private Set<UserCategoryAccess> categoryAccesses = new HashSet<>();

    /**
     * 是否是某部门的负责人（@Transient，JwtAuthFilter 加载时计算）。
     *
     * 计算逻辑：user.department != null && user.department.leader != null
     *           && user.department.leader.id == user.id
     * 部门领导可见本部门所有保密等级数据（含他人录入的）。
     */
    @Transient
    private Boolean departmentLeader = false;

    @Column(nullable = false)
    private Boolean enabled = true;

    @Column(nullable = false, updatable = false)
    private LocalDateTime createTime;

    private LocalDateTime updateTime;

    @PrePersist
    protected void onCreate() {
        createTime = LocalDateTime.now();
        updateTime = LocalDateTime.now();
    }

    @PreUpdate
    protected void onUpdate() {
        updateTime = LocalDateTime.now();
    }

    public User() {}

    // Getters and Setters
    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }

    public String getUsername() { return username; }
    public void setUsername(String username) { this.username = username; }

    public String getPassword() { return password; }
    public void setPassword(String password) { this.password = password; }

    public String getRealName() { return realName; }
    public void setRealName(String realName) { this.realName = realName; }

    public String getEmployeeNo() { return employeeNo; }
    public void setEmployeeNo(String employeeNo) { this.employeeNo = employeeNo; }

    public String getEmail() { return email; }
    public void setEmail(String email) { this.email = email; }

    public String getPhone() { return phone; }
    public void setPhone(String phone) { this.phone = phone; }

    public Role getRole() { return role; }
    public void setRole(Role role) { this.role = role; }

    public Department getDepartment() { return department; }
    public void setDepartment(Department department) { this.department = department; }

    public Set<UserConfidentialityAccess> getConfidentialityAccesses() { return confidentialityAccesses; }
    public void setConfidentialityAccesses(Set<UserConfidentialityAccess> confidentialityAccesses) {
        this.confidentialityAccesses = confidentialityAccesses;
    }

    public Set<UserCategoryAccess> getCategoryAccesses() { return categoryAccesses; }
    public void setCategoryAccesses(Set<UserCategoryAccess> categoryAccesses) {
        this.categoryAccesses = categoryAccesses;
    }

    public Boolean getDepartmentLeader() { return departmentLeader; }
    public void setDepartmentLeader(Boolean departmentLeader) { this.departmentLeader = departmentLeader; }

    public Boolean getEnabled() { return enabled; }
    public void setEnabled(Boolean enabled) { this.enabled = enabled; }

    public LocalDateTime getCreateTime() { return createTime; }
    public void setCreateTime(LocalDateTime createTime) { this.createTime = createTime; }

    public LocalDateTime getUpdateTime() { return updateTime; }
    public void setUpdateTime(LocalDateTime updateTime) { this.updateTime = updateTime; }
}
