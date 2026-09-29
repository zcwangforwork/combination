package com.insulinpump.usermgmt.dto;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;

/**
 * [SEC 2026-09-28] 用户保密密级变更请求体（方案 §12 R2 / §5.4 管理端 API）。
 */
public class SecLevelChangeRequest {

    @NotNull(message = "密级不能为空")
    @Min(value = 0, message = "密级不能小于 0")
    @Max(value = 3, message = "密级不能大于 3")
    private Integer newLevel;

    /** 变更原因，写入审计日志 */
    private String reason;

    public Integer getNewLevel() { return newLevel; }
    public void setNewLevel(Integer newLevel) { this.newLevel = newLevel; }

    public String getReason() { return reason; }
    public void setReason(String reason) { this.reason = reason; }
}
