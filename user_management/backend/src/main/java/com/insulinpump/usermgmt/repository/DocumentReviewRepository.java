package com.insulinpump.usermgmt.repository;

import com.insulinpump.usermgmt.model.DocumentReview;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;

/**
 * 文档审批记录 Repository
 */
@Repository
public interface DocumentReviewRepository extends JpaRepository<DocumentReview, Long> {

    /** 按审批时间倒序返回某文档的全部审批记录 */
    List<DocumentReview> findByDocumentIdOrderByReviewedAtDesc(Long documentId);
}
