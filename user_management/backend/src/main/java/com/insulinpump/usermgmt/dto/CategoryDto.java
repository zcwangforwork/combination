package com.insulinpump.usermgmt.dto;

/**
 * 文档分类 DTO
 */
public class CategoryDto {

    private Long id;
    private String code;
    private String name;
    private String description;
    private Integer sortOrder;
    /** 分类归属：SYSTEM=体系文档, RESEARCH=研发资料 */
    private String docType;

    public CategoryDto() {}

    public CategoryDto(Long id, String code, String name, String description, Integer sortOrder) {
        this.id = id;
        this.code = code;
        this.name = name;
        this.description = description;
        this.sortOrder = sortOrder;
    }

    public CategoryDto(Long id, String code, String name, String description, Integer sortOrder, String docType) {
        this.id = id;
        this.code = code;
        this.name = name;
        this.description = description;
        this.sortOrder = sortOrder;
        this.docType = docType;
    }

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }

    public String getCode() { return code; }
    public void setCode(String code) { this.code = code; }

    public String getName() { return name; }
    public void setName(String name) { this.name = name; }

    public String getDescription() { return description; }
    public void setDescription(String description) { this.description = description; }

    public Integer getSortOrder() { return sortOrder; }
    public void setSortOrder(Integer sortOrder) { this.sortOrder = sortOrder; }

    public String getDocType() { return docType; }
    public void setDocType(String docType) { this.docType = docType; }
}
