package com.insulinpump.usermgmt.repository;

import com.insulinpump.usermgmt.model.Notification;
import com.insulinpump.usermgmt.model.NotificationType;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.Optional;

@Repository
public interface NotificationRepository extends JpaRepository<Notification, Long> {

    /** 未读通知数（顶栏角标） */
    long countByUserIdAndReadFalse(Long userId);

    /** 通知中心分页列表（新 -> 旧） */
    Page<Notification> findByUserIdOrderByCreatedAtDesc(Long userId, Pageable pageable);

    /** 审批待办：未读的 APPROVAL_TASK（新 -> 旧） */
    List<Notification> findByUserIdAndTypeAndReadFalseOrderByCreatedAtDesc(
            Long userId, NotificationType type, Pageable pageable);

    Optional<Notification> findByIdAndUserId(Long id, Long userId);

    /** 单条标记已读 */
    @Modifying
    @Query("update Notification n set n.read = true where n.id = :id and n.userId = :userId")
    int markRead(@Param("id") Long id, @Param("userId") Long userId);

    /** 全部标记已读 */
    @Modifying
    @Query("update Notification n set n.read = true where n.userId = :userId and n.read = false")
    int markAllRead(@Param("userId") Long userId);

    /**
     * 将某关联业务的所有待办通知标记为已读。
     * 用于审批动作发生时，把"待我审批"批量置为已读，避免其他 ADMIN 看到过期待办。
     */
    @Modifying
    @Query("update Notification n set n.read = true " +
            "where n.type = :type and n.relatedType = :relatedType " +
            "and n.relatedId = :relatedId and n.read = false")
    int markTaskDoneByRelated(@Param("type") NotificationType type,
                              @Param("relatedType") String relatedType,
                              @Param("relatedId") Long relatedId);
}
