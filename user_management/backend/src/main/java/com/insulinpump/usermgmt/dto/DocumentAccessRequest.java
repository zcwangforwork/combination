package com.insulinpump.usermgmt.dto;

import java.util.List;

/**
 * 按资料授权请求 DTO
 *
 * 用于 PUT /api/users/{id}/document-access 接口，批量给指定用户授予"查看某份研发资料"权限。
 *
 * documentIds: RESEARCH 资料文档 ID 列表（SYSTEM 文档与 TOP_SECRET 资料会被拒绝，整批不写入）
 */
public class DocumentAccessRequest {

    private List<Long> documentIds;

    public List<Long> getDocumentIds() { return documentIds; }
    public void setDocumentIds(List<Long> documentIds) { this.documentIds = documentIds; }
}
