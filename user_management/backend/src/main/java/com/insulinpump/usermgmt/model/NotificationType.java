package com.insulinpump.usermgmt.model;

/**
 * 通知类型
 *
 * 与待办/通知中心的对应关系：
 *  - APPROVAL_TASK       待我审批（发给所有 ADMIN，文档提交评审后生成）—— 计入"审批待办"
 *  - APPROVAL_RESULT     审批结果（发给文档上传人，审批通过/驳回后生成）
 *  - CONFIDENTIALITY_GRANT  保密等级授权（发给被授权员工）
 *  - CATEGORY_GRANT      资料分类授权（发给被授权员工）
 *  - DOCUMENT_SHARE      文档分享（发给被分享同事）
 *  - SYSTEM_ANNOUNCEMENT 系统公告（ADMIN 发布，广播给所有启用用户）
 */
public enum NotificationType {
    APPROVAL_TASK,
    APPROVAL_RESULT,
    CONFIDENTIALITY_GRANT,
    CATEGORY_GRANT,
    DOCUMENT_SHARE,
    SYSTEM_ANNOUNCEMENT
}
