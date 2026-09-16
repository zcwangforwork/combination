package com.insulinpump.usermgmt.model;

import jakarta.persistence.*;
import java.time.LocalDateTime;

/**
 * 站内通知实体
 *
 * 每条通知面向单个收件人（userId）。同一事件发给多个收件人时，为每个收件人各建一条。
 * 文档审批待办（APPROVAL_TASK）在审批动作发生时按 relatedType+relatedId 批量置为已读，
 * 避免多个 ADMIN 看到同一个"待我审批"。
 *
 * 字段说明:
 *   - type           通知类型（见 NotificationType）
 *   - title/content  标题 / 内容
 *   - relatedType    关联业务类型（DOCUMENT / USER 等）
 *   - relatedId      关联业务主键（用于前端跳转）
 *   - link           前端路由链接（如 /documents/123）
 *   - read           是否已读（默认 false）
 */
@Entity
@Table(name = "t_notification")
public class Notification {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    /** 收件人用户 ID */
    @Column(name = "user_id", nullable = false)
    private Long userId;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 30)
    private NotificationType type;

    @Column(nullable = false, length = 200)
    private String title;

    @Column(nullable = false, length = 1000)
    private String content;

    /** 关联业务类型（DOCUMENT / USER 等），供前端跳转定位 */
    @Column(length = 30)
    private String relatedType;

    @Column(name = "related_id")
    private Long relatedId;

    /** 前端路由链接，如 /documents/123 */
    @Column(length = 200)
    private String link;

    @Column(nullable = false)
    private Boolean read = false;

    @Column(nullable = false, updatable = false)
    private LocalDateTime createdAt;

    @PrePersist
    protected void onCreate() {
        createdAt = LocalDateTime.now();
    }

    public Notification() {}

    public Notification(Long userId, NotificationType type, String title, String content,
                        String relatedType, Long relatedId, String link) {
        this.userId = userId;
        this.type = type;
        this.title = title;
        this.content = content;
        this.relatedType = relatedType;
        this.relatedId = relatedId;
        this.link = link;
    }

    // ============ Getters and Setters ============

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }

    public Long getUserId() { return userId; }
    public void setUserId(Long userId) { this.userId = userId; }

    public NotificationType getType() { return type; }
    public void setType(NotificationType type) { this.type = type; }

    public String getTitle() { return title; }
    public void setTitle(String title) { this.title = title; }

    public String getContent() { return content; }
    public void setContent(String content) { this.content = content; }

    public String getRelatedType() { return relatedType; }
    public void setRelatedType(String relatedType) { this.relatedType = relatedType; }

    public Long getRelatedId() { return relatedId; }
    public void setRelatedId(Long relatedId) { this.relatedId = relatedId; }

    public String getLink() { return link; }
    public void setLink(String link) { this.link = link; }

    public Boolean getRead() { return read; }
    public void setRead(Boolean read) { this.read = read; }

    public LocalDateTime getCreatedAt() { return createdAt; }
    public void setCreatedAt(LocalDateTime createdAt) { this.createdAt = createdAt; }
}
