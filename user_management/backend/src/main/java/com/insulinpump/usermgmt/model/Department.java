package com.insulinpump.usermgmt.model;

import jakarta.persistence.*;
import java.time.LocalDateTime;

@Entity
@Table(name = "t_department")
public class Department {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true, length = 100)
    private String name;

    @Column(length = 200)
    private String description;

    @Column
    private Long parentId;

    /**
     * 部门负责人（FK -> t_user）。
     *
     * 部门负责人可见本部门所有保密等级的数据（含他人录入的）。
     * 单领导模式：一个部门一个 leader；一个 user 可领导多个部门（轮岗场景）。
     * 调岗风险：admin 手工更新 leader_id，无自动审计（参见开发计划 GAP #4）。
     */
    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "leader_id",
        foreignKey = @ForeignKey(name = "fk_department_leader"))
    private User leader;

    @Column(nullable = false, updatable = false)
    private LocalDateTime createTime;

    @PrePersist
    protected void onCreate() {
        createTime = LocalDateTime.now();
    }

    public Department() {}

    public Department(String name, String description, Long parentId) {
        this.name = name;
        this.description = description;
        this.parentId = parentId;
    }

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }

    public String getName() { return name; }
    public void setName(String name) { this.name = name; }

    public String getDescription() { return description; }
    public void setDescription(String description) { this.description = description; }

    public Long getParentId() { return parentId; }
    public void setParentId(Long parentId) { this.parentId = parentId; }

    public User getLeader() { return leader; }
    public void setLeader(User leader) { this.leader = leader; }

    public LocalDateTime getCreateTime() { return createTime; }
    public void setCreateTime(LocalDateTime createTime) { this.createTime = createTime; }
}
