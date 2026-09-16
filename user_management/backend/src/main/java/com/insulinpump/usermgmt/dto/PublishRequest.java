package com.insulinpump.usermgmt.dto;

/**
 * 发布文档请求 DTO
 *
 * - changeLog: 变更说明，描述本次发布相对上一版本改了什么。可选（首次发布可省略）。
 * - password:  电子签名密码（必填，FDA Part 11 合规）
 * - meaning:   签名含义（必填，如"我批准此文档版本发布生效"）
 */
public class PublishRequest {

    private String changeLog;
    private String password;
    private String meaning;

    public String getChangeLog() { return changeLog; }
    public void setChangeLog(String changeLog) { this.changeLog = changeLog; }

    public String getPassword() { return password; }
    public void setPassword(String password) { this.password = password; }

    public String getMeaning() { return meaning; }
    public void setMeaning(String meaning) { this.meaning = meaning; }
}
