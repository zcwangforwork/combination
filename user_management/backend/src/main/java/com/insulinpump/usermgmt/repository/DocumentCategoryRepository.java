package com.insulinpump.usermgmt.repository;

import com.insulinpump.usermgmt.model.DocumentCategory;
import com.insulinpump.usermgmt.model.DocumentType;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;

public interface DocumentCategoryRepository extends JpaRepository<DocumentCategory, Long> {

    Optional<DocumentCategory> findByCode(String code);

    boolean existsByCode(String code);

    /**
     * 按文档类型查询分类列表（用于研发资料/体系文档各自的下拉列表）
     */
    List<DocumentCategory> findByDocTypeOrderBySortOrderAsc(DocumentType docType);
}
