package com.insulinpump.usermgmt.model;

import jakarta.persistence.*;
import org.hibernate.annotations.Immutable;

import java.time.LocalDateTime;

/**
 * 审计日志实体（不可变，INSERT only）
 *
 * 记录所有写操作的审计追踪：谁/何时/做了什么/改了什么/结果如何。
 * 法规依据：FDA 21 CFR Part 820 / ISO 13485 4.2.5 / 中国 GMP。
 *
 * 不可篡改保证：
 *  1. JPA 层：@Immutable + 不提供 setter for timestamp
 *  2. DB 层：PostgreSQL REVOKE UPDATE, DELETE ON t_audit_log
 *  3. 应用层：AuditLogRepository 不暴露 delete/update 方法
 *
 * 关系图:
 *   t_audit_log
 *      ├── user_id       -> t_user   (N:1, 仅存 id, 不做 FK, 避免用户删除导致审计断链)
 *      └── signature_id  -> t_signature_record (N:1, 仅存 id, 可空)
 */
@Entity
@Table(name = "t_audit_log", indexes = {
        @Index(name = "idx_audit_user_time", columnList = "user_id, timestamp"),
        @Index(name = "idx_audit_entity_time", columnList = "entity_type, entity_id, timestamp"),
        @Index(name = "idx_audit_action_time", columnList = "action, timestamp"),
        @Index(name = "idx_audit_result_time", columnList = "result, timestamp")
})
@Immutable
public class AuditLog {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    /** 操作人 ID（仅存 id，不做 FK 关联，避免用户删除导致审计断链） */
    @Column(name = "user_id", nullable = false)
    private Long userId;

    /** 操作人用户名（冗余存储，用户改名后仍可追溯） */
    @Column(nullable = false, length = 50)
    private String username;

    /** 操作类型: PUBLISH / APPROVE / REJECT / RETIRE / ROLLBACK / UPLOAD / UPDATE / DELETE / DOWNLOAD / CHECKSUM_MISMATCH */
    @Column(nullable = false, length = 30)
    private String action;

    /** 实体类型: DOCUMENT / EMPLOYEE / RESEARCH_DATA / SUPPLIER ... */
    @Column(nullable = false, length = 30)
    private String entityType;

    /** 实体 ID（可空，如批量删除） */
    private Long entityId;

    /** 变更前状态（JSON，由 Service 层通过 AuditContext 提供） */
    @Column(columnDefinition = "text")
    private String beforeJson;

    /** 变更后状态（JSON，由 AOP 切面从返回值序列化） */
    @Column(columnDefinition = "text")
    private String afterJson;

    /** 操作结果: SUCCESS / FAILURE */
    @Column(nullable = false, length = 10)
    private String result;

    /** 失败时的错误信息 */
    @Column(length = 1000)
    private String errorMsg;

    /** 客户端 IP */
    @Column(length = 50)
    private String ip;

    /** User-Agent */
    @Column(length = 500)
    private String userAgent;

    /** 关联的签名记录 ID（如果该操作有电子签名） */
    @Column(name = "signature_id")
    private Long signatureId;

    @Column(nullable = false, updatable = false)
    private LocalDateTime timestamp;

    @PrePersist
    protected void onCreate() {
        timestamp = LocalDateTime.now();
    }

    // ============ Getters and Setters ============

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }

    public Long getUserId() { return userId; }
    public void setUserId(Long userId) { this.userId = userId; }

    public String getUsername() { return username; }
    public void setUsername(String username) { this.username = username; }

    public String getAction() { return action; }
    public void setAction(String action) { this.action = action; }

    public String getEntityType() { return entityType; }
    public void setEntityType(String entityType) { this.entityType = entityType; }

    public Long getEntityId() { return entityId; }
    public void setEntityId(Long entityId) { this.entityId = entityId; }

    public String getBeforeJson() { return beforeJson; }
    public void setBeforeJson(String beforeJson) { this.beforeJson = beforeJson; }

    public String getAfterJson() { return afterJson; }
    public void setAfterJson(String afterJson) { this.afterJson = afterJson; }

    public String getResult() { return result; }
    public void setResult(String result) { this.result = result; }

    public String getErrorMsg() { return errorMsg; }
    public void setErrorMsg(String errorMsg) { this.errorMsg = errorMsg; }

    public String getIp() { return ip; }
    public void setIp(String ip) { this.ip = ip; }

    public String getUserAgent() { return userAgent; }
    public void setUserAgent(String userAgent) { this.userAgent = userAgent; }

    public Long getSignatureId() { return signatureId; }
    public void setSignatureId(Long signatureId) { this.signatureId = signatureId; }

    public LocalDateTime getTimestamp() { return timestamp; }
    public void setTimestamp(LocalDateTime timestamp) { this.timestamp = timestamp; }
}
