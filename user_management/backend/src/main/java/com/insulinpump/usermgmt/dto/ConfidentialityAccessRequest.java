package com.insulinpump.usermgmt.dto;

/**
 * 保密等级授权请求 DTO
 *
 * 用于 PUT /api/users/{id}/confidentiality-access 接口，
 * 给指定用户授予或更新某保密等级的访问权限。
 *
 * confidentialityLevel: PUBLIC / INTERNAL / CONFIDENTIAL / TOP_SECRET
 * accessMode: READ_ONLY（默认，只读）/ READ_WRITE（可读写）
 *   已存在该等级的授权时，本字段可用来切换读写模式（只读 -> 可读写 或反之）。
 */
public class ConfidentialityAccessRequest {

    private String confidentialityLevel;

    private String accessMode;

    public String getConfidentialityLevel() { return confidentialityLevel; }
    public void setConfidentialityLevel(String confidentialityLevel) { this.confidentialityLevel = confidentialityLevel; }

    public String getAccessMode() { return accessMode; }
    public void setAccessMode(String accessMode) { this.accessMode = accessMode; }
}
