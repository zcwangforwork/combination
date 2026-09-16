package com.insulinpump.usermgmt.service;

import com.insulinpump.usermgmt.dto.CategoryDto;
import com.insulinpump.usermgmt.model.DocumentCategory;
import com.insulinpump.usermgmt.model.DocumentType;
import com.insulinpump.usermgmt.repository.DocumentCategoryRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.stream.Collectors;

/**
 * 文档分类 Service
 */
@Service
public class DocumentCategoryService {

    private final DocumentCategoryRepository categoryRepository;

    public DocumentCategoryService(DocumentCategoryRepository categoryRepository) {
        this.categoryRepository = categoryRepository;
    }

    public List<CategoryDto> listAll() {
        return categoryRepository.findAll().stream()
                .sorted(this::compareBySortOrder)
                .map(this::toDto)
                .collect(Collectors.toList());
    }

    /**
     * 按文档类型查询分类（用于研发资料/体系文档各自的下拉列表）
     */
    public List<CategoryDto> listByDocType(DocumentType docType) {
        return categoryRepository.findByDocTypeOrderBySortOrderAsc(docType).stream()
                .map(this::toDto)
                .collect(Collectors.toList());
    }

    public DocumentCategory getById(Long id) {
        return categoryRepository.findById(id)
                .orElseThrow(() -> new IllegalArgumentException("分类不存在"));
    }

    @Transactional
    public CategoryDto create(String code, String name, String description, Integer sortOrder) {
        if (categoryRepository.existsByCode(code)) {
            throw new IllegalArgumentException("分类编码已存在: " + code);
        }
        DocumentCategory category = new DocumentCategory(code, name, description, sortOrder);
        return toDto(categoryRepository.save(category));
    }

    private int compareBySortOrder(DocumentCategory a, DocumentCategory b) {
        if (a.getSortOrder() == null && b.getSortOrder() == null) return 0;
        if (a.getSortOrder() == null) return 1;
        if (b.getSortOrder() == null) return -1;
        return a.getSortOrder().compareTo(b.getSortOrder());
    }

    private CategoryDto toDto(DocumentCategory c) {
        return new CategoryDto(
                c.getId(), c.getCode(), c.getName(), c.getDescription(),
                c.getSortOrder(),
                c.getDocType() != null ? c.getDocType().name() : null
        );
    }
}
