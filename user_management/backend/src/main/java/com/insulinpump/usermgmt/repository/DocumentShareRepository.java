package com.insulinpump.usermgmt.repository;

import com.insulinpump.usermgmt.model.DocumentShare;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.List;

/**
 * 文档分享关系 Repository
 *
 * 核心查询：
 *  - existsByDocumentIdAndSharedWithUserId: 可见性校验（单文档）
 *  - findDocumentIdsBySharedWithUserId: 列表查询（获取分享给我的所有文档 ID）
 *  - findByDocumentId: 分享管理（列出某文档的所有分享记录）
 */
public interface DocumentShareRepository extends JpaRepository<DocumentShare, Long> {

    /**
     * 检查某文档是否已分享给某用户（可见性校验用）
     */
    boolean existsByDocumentIdAndSharedWithUserId(Long documentId, Long sharedWithUserId);

    /**
     * 查询分享给某用户的所有文档 ID（列表查询用）
     */
    @Query("SELECT ds.documentId FROM DocumentShare ds WHERE ds.sharedWithUserId = :userId")
    List<Long> findDocumentIdsBySharedWithUserId(@Param("userId") Long userId);

    /**
     * 查询分享给某用户的全部分享记录（按资料授权清单查询用）
     */
    List<DocumentShare> findBySharedWithUserId(Long userId);

    /**
     * 查询某文档的所有分享记录（分享管理用）
     */
    List<DocumentShare> findByDocumentId(Long documentId);

    /**
     * 删除某文档与某用户的分享关系
     */
    @Modifying
    void deleteByDocumentIdAndSharedWithUserId(Long documentId, Long sharedWithUserId);

    /**
     * 删除某文档的所有分享记录（文档删除时级联清理）
     */
    @Modifying
    void deleteByDocumentId(Long documentId);
}
