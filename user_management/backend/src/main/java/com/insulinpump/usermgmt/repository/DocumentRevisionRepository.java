package com.insulinpump.usermgmt.repository;

import com.insulinpump.usermgmt.model.DocumentRevision;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;

/**
 * 文档修订历史 Repository
 *
 * 查询模式:
 *  - findByDocumentIdOrderByPublishedAtDesc: 列出某文档全部修订历史（最新在前）
 *  - findTopByDocumentIdOrderByPublishedAtDesc: 获取最新一条修订（用于确定版本链末端）
 *  - countByDocumentId: 统计修订次数（用于版本号计算）
 */
public interface DocumentRevisionRepository extends JpaRepository<DocumentRevision, Long> {

    List<DocumentRevision> findByDocumentIdOrderByPublishedAtDesc(Long documentId);

    Optional<DocumentRevision> findTopByDocumentIdOrderByPublishedAtDesc(Long documentId);

    long countByDocumentId(Long documentId);
}
