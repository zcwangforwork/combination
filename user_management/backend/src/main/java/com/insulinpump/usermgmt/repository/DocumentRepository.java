package com.insulinpump.usermgmt.repository;

import com.insulinpump.usermgmt.model.Document;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.JpaSpecificationExecutor;

import java.util.List;

/**
 * 文档 Repository
 *
 * 使用 JpaSpecificationExecutor 替代 @Query，通过 Criteria API 显式控制参数类型，
 * 避免 Hibernate 6 在绑定 null String 参数时默认使用 bytea 类型导致的 SQL 错误。
 *
 * 可见性/分类/关键字过滤逻辑见 DocumentService.buildSpecification()
 */
public interface DocumentRepository extends JpaRepository<Document, Long>,
        JpaSpecificationExecutor<Document> {

    /**
     * 查找所有 status 为 null 的文档（用于数据迁移：旧数据升级为版本化模型）
     */
    List<Document> findByStatusIsNull();
}
