package com.insulinpump.usermgmt.dto;

import jakarta.validation.constraints.NotBlank;

import java.util.Map;

/**
 * 文档更新请求 DTO
 */
public class DocumentUpdateRequest {

    private String title;
    private String description;
    private Long categoryId;
    private String visibility;
    /** 保密等级（仅 RESEARCH 类型使用）：PUBLIC/INTERNAL/CONFIDENTIAL/TOP_SECRET */
    private String confidentialityLevel;

    /**
     * 来源溯源（仅 RESEARCH 原理文档使用，III 类医疗器械合规）
     * 字段：{origin(FACTORY/THIRD_PARTY/COMMON), thirdPartyName, obtainedDate, agreementNo}
     * 传入 null 表示不修改；传入空 Map 表示清空。
     */
    private Map<String, Object> sourceProvenance;

    public String getTitle() { return title; }
    public void setTitle(String title) { this.title = title; }

    public String getDescription() { return description; }
    public void setDescription(String description) { this.description = description; }

    public Long getCategoryId() { return categoryId; }
    public void setCategoryId(Long categoryId) { this.categoryId = categoryId; }

    public String getVisibility() { return visibility; }
    public void setVisibility(String visibility) { this.visibility = visibility; }

    public String getConfidentialityLevel() { return confidentialityLevel; }
    public void setConfidentialityLevel(String confidentialityLevel) { this.confidentialityLevel = confidentialityLevel; }

    public Map<String, Object> getSourceProvenance() { return sourceProvenance; }
    public void setSourceProvenance(Map<String, Object> sourceProvenance) { this.sourceProvenance = sourceProvenance; }
}
