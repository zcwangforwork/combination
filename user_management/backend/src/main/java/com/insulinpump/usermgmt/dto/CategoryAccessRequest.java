package com.insulinpump.usermgmt.dto;

import java.util.List;

/**
 * 资料分类授权请求 DTO
 *
 * 用于 PUT /api/users/{id}/category-access 接口，批量给指定用户授予资料分类访问权限。
 *
 * categoryIds: RESEARCH 分类 ID 列表（SYSTEM 分类会被拒绝，整批不写入）
 * accessMode: READ_ONLY（默认，只读）/ READ_WRITE（可读写）
 *   对本次请求中的所有分类生效（新建 + 已存在都会更新为该模式）。
 */
public class CategoryAccessRequest {

    private List<Long> categoryIds;

    private String accessMode;

    public List<Long> getCategoryIds() { return categoryIds; }
    public void setCategoryIds(List<Long> categoryIds) { this.categoryIds = categoryIds; }

    public String getAccessMode() { return accessMode; }
    public void setAccessMode(String accessMode) { this.accessMode = accessMode; }
}
