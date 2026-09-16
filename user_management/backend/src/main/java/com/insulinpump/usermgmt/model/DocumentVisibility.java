package com.insulinpump.usermgmt.model;

/**
 * 文档可见性枚举
 *
 * PUBLIC      - 全员可见
 * DEPARTMENT  - 上传人所在部门可见
 * ASSIGNEES   - 指定人员可见（MVP 预留，暂不实现指定人员表）
 */
public enum DocumentVisibility {
    PUBLIC,
    DEPARTMENT,
    ASSIGNEES
}
