package com.insulinpump.usermgmt.dto;

/**
 * 审批决策请求（approve / reject 共用）
 *
 * - approve: comment 可选（审批意见）
 * - reject:  comment 必填（驳回理由，Service 层强制校验）
 * - password: 电子签名密码（必填，FDA Part 11 合规）
 * - meaning:  签名含义（必填，如"我审批通过此文档"）
 */
public class ReviewDecisionRequest {

    private String comment;
    private String password;
    private String meaning;

    public ReviewDecisionRequest() {}

    public String getComment() { return comment; }
    public void setComment(String comment) { this.comment = comment; }

    public String getPassword() { return password; }
    public void setPassword(String password) { this.password = password; }

    public String getMeaning() { return meaning; }
    public void setMeaning(String meaning) { this.meaning = meaning; }
}
