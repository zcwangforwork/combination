package com.insulinpump.usermgmt.model;

import jakarta.persistence.*;
import org.hibernate.annotations.Immutable;

import java.time.LocalDateTime;

/**
 * 电子签名记录（不可变，INSERT only）
 *
 * FDA 21 CFR Part 11 合规：电子签名等同于手写签名，
 * 必须包含三要素：签名者身份 + 签名时间 + 签名含义。
 *
 * 签名哈希算法：SHA-256(userId|username|realName|action|entityType|entityId|meaning|signedAt|passwordHash)
 * 包含 BCrypt 密码哈希是为了绑定签名时刻的密码状态（密码改了之后旧签名不可复现）。
 *
 * 关系图:
 *   t_signature_record
 *      └── user_id -> t_user (N:1, 仅存 id)
 */
@Entity
@Table(name = "t_signature_record", indexes = {
        @Index(name = "idx_sig_entity", columnList = "entity_type, entity_id, signed_at"),
        @Index(name = "idx_sig_user", columnList = "user_id, signed_at")
})
@Immutable
public class SignatureRecord {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "user_id", nullable = false)
    private Long userId;

    @Column(nullable = false, length = 50)
    private String username;

    /** 签名者真实姓名（FDA Part 11 要求签名者身份可识别） */
    @Column(nullable = false, length = 50)
    private String realName;

    /** 签名动作: PUBLISH / APPROVE / REJECT / RETIRE / ROLLBACK */
    @Column(nullable = false, length = 30)
    private String action;

    @Column(nullable = false, length = 30)
    private String entityType;

    @Column(nullable = false)
    private Long entityId;

    /** 签名含义（用户填写的"我批准xxx"） */
    @Column(nullable = false, length = 500)
    private String meaning;

    /** 签名哈希（SHA-256） */
    @Column(nullable = false, length = 64)
    private String signatureHash;

    /** 签名时刻用户的密码哈希快照（BCrypt），绑定密码状态 */
    @Column(nullable = false, length = 60)
    private String passwordHashSnapshot;

    @Column(length = 50)
    private String ip;

    @Column(length = 500)
    private String userAgent;

    @Column(nullable = false, updatable = false)
    private LocalDateTime signedAt;

    @PrePersist
    protected void onSign() {
        signedAt = LocalDateTime.now();
    }

    // ============ Getters and Setters ============

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }

    public Long getUserId() { return userId; }
    public void setUserId(Long userId) { this.userId = userId; }

    public String getUsername() { return username; }
    public void setUsername(String username) { this.username = username; }

    public String getRealName() { return realName; }
    public void setRealName(String realName) { this.realName = realName; }

    public String getAction() { return action; }
    public void setAction(String action) { this.action = action; }

    public String getEntityType() { return entityType; }
    public void setEntityType(String entityType) { this.entityType = entityType; }

    public Long getEntityId() { return entityId; }
    public void setEntityId(Long entityId) { this.entityId = entityId; }

    public String getMeaning() { return meaning; }
    public void setMeaning(String meaning) { this.meaning = meaning; }

    public String getSignatureHash() { return signatureHash; }
    public void setSignatureHash(String signatureHash) { this.signatureHash = signatureHash; }

    public String getPasswordHashSnapshot() { return passwordHashSnapshot; }
    public void setPasswordHashSnapshot(String passwordHashSnapshot) { this.passwordHashSnapshot = passwordHashSnapshot; }

    public String getIp() { return ip; }
    public void setIp(String ip) { this.ip = ip; }

    public String getUserAgent() { return userAgent; }
    public void setUserAgent(String userAgent) { this.userAgent = userAgent; }

    public LocalDateTime getSignedAt() { return signedAt; }
    public void setSignedAt(LocalDateTime signedAt) { this.signedAt = signedAt; }
}
