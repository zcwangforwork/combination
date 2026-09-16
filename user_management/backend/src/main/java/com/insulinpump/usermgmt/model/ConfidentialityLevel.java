package com.insulinpump.usermgmt.model;

/**
 * 保密等级枚举（仅用于 RESEARCH 研发资料）
 *
 * 权限矩阵：
 *   PUBLIC      (公开)  - owner + shared + ADMIN 可见，可分享，可下载
 *   INTERNAL    (内部)  - owner + shared + ADMIN 可见，可分享，可下载（默认）
 *   CONFIDENTIAL(机密)  - owner + shared + ADMIN 可见，仅可分享给同部门，可下载
 *   TOP_SECRET  (绝密)  - owner + ADMIN 可见，不可分享，仅 owner+ADMIN 可下载
 */
public enum ConfidentialityLevel {
    PUBLIC,
    INTERNAL,
    CONFIDENTIAL,
    TOP_SECRET
}
