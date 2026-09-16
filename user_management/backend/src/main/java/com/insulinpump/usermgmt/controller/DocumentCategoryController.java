package com.insulinpump.usermgmt.controller;

import com.insulinpump.usermgmt.dto.ApiResponse;
import com.insulinpump.usermgmt.dto.CategoryDto;
import com.insulinpump.usermgmt.model.DocumentType;
import com.insulinpump.usermgmt.service.DocumentCategoryService;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;

import java.util.List;

/**
 * 文档分类 Controller
 *
 * 支持按 docType 筛选：
 *   GET /api/document-categories           - 全部分类
 *   GET /api/document-categories?docType=RESEARCH  - 仅研发资料分类
 *   GET /api/document-categories?docType=SYSTEM    - 仅体系文档分类
 */
@RestController
@RequestMapping("/api/document-categories")
public class DocumentCategoryController {

    private final DocumentCategoryService categoryService;

    public DocumentCategoryController(DocumentCategoryService categoryService) {
        this.categoryService = categoryService;
    }

    @GetMapping
    public ResponseEntity<ApiResponse<List<CategoryDto>>> list(
            @RequestParam(required = false) String docType) {
        List<CategoryDto> result;
        if (docType != null && !docType.isBlank()) {
            DocumentType type = DocumentType.valueOf(docType.toUpperCase());
            result = categoryService.listByDocType(type);
        } else {
            result = categoryService.listAll();
        }
        return ResponseEntity.ok(ApiResponse.success(result));
    }

    @PostMapping
    @PreAuthorize("hasRole('ADMIN')")
    public ResponseEntity<ApiResponse<CategoryDto>> create(
            @RequestParam String code,
            @RequestParam String name,
            @RequestParam(required = false) String description,
            @RequestParam(required = false) Integer sortOrder) {
        CategoryDto dto = categoryService.create(code, name, description, sortOrder);
        return ResponseEntity.ok(ApiResponse.success("创建成功", dto));
    }
}
