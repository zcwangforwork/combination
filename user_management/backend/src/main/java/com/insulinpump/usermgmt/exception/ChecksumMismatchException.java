package com.insulinpump.usermgmt.exception;

/**
 * 文件完整性校验失败异常
 *
 * 当下载/读取文件时重算 SHA-256 与存储的 checksum 不匹配时抛出。
 * GlobalExceptionHandler 捕获后返回 410 Gone + 错误信息。
 *
 * ALCOA+ 数据完整性：文件可能已被篡改，拒绝提供内容。
 */
public class ChecksumMismatchException extends RuntimeException {

    private final Long entityId;
    private final String entityType;

    public ChecksumMismatchException(String message, Long entityId, String entityType) {
        super(message);
        this.entityId = entityId;
        this.entityType = entityType;
    }

    public Long getEntityId() { return entityId; }
    public String getEntityType() { return entityType; }
}
