package com.insulinpump.usermgmt.model;

/**
 * 文档审批决策枚举
 *
 *   APPROVED - 审批通过，文档进入 PUBLISHED
 *   REJECTED - 审批驳回，文档退回 DRAFT
 */
public enum ReviewDecision {
    APPROVED,
    REJECTED
}
