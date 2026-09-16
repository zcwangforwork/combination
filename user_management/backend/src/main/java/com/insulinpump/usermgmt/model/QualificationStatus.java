package com.insulinpump.usermgmt.model;

/**
 * 供应商合格状态枚举
 *
 *   QUALIFIED  - 合格供应商（已通过审核）
 *   PENDING    - 待审核
 *   SUSPENDED  - 已暂停（暂停合作）
 */
public enum QualificationStatus {
    QUALIFIED,
    PENDING,
    SUSPENDED
}
