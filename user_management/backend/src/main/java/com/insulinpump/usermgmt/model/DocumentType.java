package com.insulinpump.usermgmt.model;

/**
 * 文档类型枚举（鉴别器）
 *
 * SYSTEM   - 体系文档（受控发布，组织拥有，ADMIN/SYSTEM_ENGINEER 可上传）
 * RESEARCH - 研发资料（个人私有+可分享，任何认证用户可上传，owner=上传人）
 *
 * 关系图：
 *   t_document.doc_type 决定该文档走哪套权限/可见性/文件白名单逻辑
 *
 *   SYSTEM  → PUBLIC / DEPARTMENT / ASSIGNEES 可见性 + 严格文件白名单 + ADMIN/SYS_ENG 上传
 *   RESEARCH → Owner + Shared 可见性 + 宽松文件白名单 + 任何认证用户上传
 */
public enum DocumentType {
    SYSTEM,
    RESEARCH
}
