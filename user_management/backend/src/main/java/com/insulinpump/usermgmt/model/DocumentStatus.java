package com.insulinpump.usermgmt.model;

/**
 * 文档状态枚举
 *
 * 状态机（双路径：直接发布 / 审批流）:
 *
 *   路径一：直接发布（ADMIN 或上传人跳过审批）
 *   ┌───────┐  publish(首次)  ┌───────────┐  publish(新版本)  ┌───────────┐  retire  ┌──────────┐
 *   │ DRAFT │ ──────────────> │ PUBLISHED │ ────────────────> │ PUBLISHED │ ───────> │ OBSOLETE │
 *   └───────┘                 └───────────┘   (快照旧版本)     └──────────┘          └──────────┘
 *
 *   路径二：审批工作流（上传人提交，ADMIN 审批）
 *   ┌───────┐  submitReview  ┌────────┐  approve  ┌───────────┐  retire  ┌──────────┐
 *   │ DRAFT │ ─────────────> │ REVIEW │ ────────> │ PUBLISHED │ ───────> │ OBSOLETE │
 *   └───────┘                 └────────┘           (创建 Revision, v1.0)  └──────────┘
 *       ^                          │
 *       │      reject(回退)        │
 *       └──────────────────────────┘
 *
 *   每次 approve/reject 创建一条 DocumentReview 记录（不可变，构成审批历史）。
 *   approve 复用 doPublish 内部逻辑（创建 Revision 快照、版本号递增）。
 *   reject 不创建 Revision（被驳回，不发布），versionAfter=null。
 *
 *   状态转换权限:
 *     - publish/submitReview: ADMIN 或上传人
 *     - approve/reject/retire: 仅 ADMIN
 */
public enum DocumentStatus {
    DRAFT,      // 草稿，编辑中，未发布
    REVIEW,     // 审核中（待 ADMIN 审批）
    PUBLISHED,  // 已发布，当前生效
    OBSOLETE    // 已作废
}
