package com.insulinpump.usermgmt.service;

import com.insulinpump.usermgmt.dto.NotificationDto;
import com.insulinpump.usermgmt.dto.NotificationStatsDto;
import com.insulinpump.usermgmt.model.Notification;
import com.insulinpump.usermgmt.model.NotificationType;
import com.insulinpump.usermgmt.model.User;
import com.insulinpump.usermgmt.repository.NotificationRepository;
import com.insulinpump.usermgmt.repository.UserRepository;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.stream.Collectors;

/**
 * 站内通知 Service
 *
 * 职责：
 *  - 生成通知（单个收件人 / 广播给所有 ADMIN / 广播给所有启用用户）
 *  - 查询当前用户的未读统计、通知列表、审批待办
 *  - 标记已读（单条 / 全部 / 按关联业务批量关闭待办）
 *
 * 与业务模块的集成点（调用方无需关心通知细节，只调 Service）：
 *  - DocumentService.submitForReview -> notifyAdmins(APPROVAL_TASK)  + 待办
 *  - DocumentService.approve/reject  -> markTaskDoneByRelated + 通知上传人(APPROVAL_RESULT)
 *  - DocumentService.share           -> 通知被分享人(DOCUMENT_SHARE)
 *  - ConfidentialityAccessController -> 通知被授权人(CONFIDENTIALITY_GRANT)
 *  - CategoryAccessController        -> 通知被授权人(CATEGORY_GRANT)
 *  - NotificationController.announcement -> broadcast(SYSTEM_ANNOUNCEMENT)
 */
@Service
public class NotificationService {

    private final NotificationRepository notificationRepository;
    private final UserRepository userRepository;

    public NotificationService(NotificationRepository notificationRepository,
                               UserRepository userRepository) {
        this.notificationRepository = notificationRepository;
        this.userRepository = userRepository;
    }

    // ============ 生成 ============

    /**
     * 给单个用户创建通知。
     * 跳过不存在的收件人（容错：目标用户已被删除时静默跳过）。
     */
    @Transactional
    public void create(Long userId, NotificationType type, String title, String content,
                       String relatedType, Long relatedId, String link) {
        if (userId == null || !userRepository.existsById(userId)) {
            return;
        }
        notificationRepository.save(new Notification(
                userId, type, title, content, relatedType, relatedId, link));
    }

    /**
     * 广播给所有启用状态的 ADMIN（用于审批待办）。
     */
    @Transactional
    public void notifyAdmins(NotificationType type, String title, String content,
                             String relatedType, Long relatedId, String link) {
        List<User> admins = userRepository.findByEnabledTrueAndRole_Code("ADMIN");
        for (User admin : admins) {
            notificationRepository.save(new Notification(
                    admin.getId(), type, title, content, relatedType, relatedId, link));
        }
    }

    /**
     * 广播给所有启用状态的用户（用于系统公告）。
     * @return 实际创建的条数
     */
    @Transactional
    public int broadcast(NotificationType type, String title, String content,
                         String relatedType, Long relatedId, String link) {
        List<User> users = userRepository.findByEnabledTrue();
        for (User user : users) {
            notificationRepository.save(new Notification(
                    user.getId(), type, title, content, relatedType, relatedId, link));
        }
        return users.size();
    }

    /**
     * 将某关联业务下未读的指定类型通知全部置为已读。
     * 用于审批动作发生时关闭所有 ADMIN 的"待我审批"待办。
     */
    @Transactional
    public void markTaskDoneByRelated(NotificationType type, String relatedType, Long relatedId) {
        notificationRepository.markTaskDoneByRelated(type, relatedType, relatedId);
    }

    // ============ 查询 ============

    /** 通知中心分页列表（新 -> 旧） */
    public Page<NotificationDto> list(Long userId, int page, int size) {
        Pageable pageable = PageRequest.of(page, size);
        return notificationRepository.findByUserIdOrderByCreatedAtDesc(userId, pageable)
                .map(this::toDto);
    }

    /** 顶栏角标：未读总数 + 审批待办数 */
    public NotificationStatsDto stats(Long userId) {
        long unread = notificationRepository.countByUserIdAndReadFalse(userId);
        long todo = notificationRepository.findByUserIdAndTypeAndReadFalseOrderByCreatedAtDesc(
                        userId, NotificationType.APPROVAL_TASK, PageRequest.of(0, 1)).size();
        return new NotificationStatsDto(unread, todo);
    }

    /** 审批待办列表（未读的 APPROVAL_TASK） */
    public List<NotificationDto> todos(Long userId) {
        List<Notification> tasks = notificationRepository
                .findByUserIdAndTypeAndReadFalseOrderByCreatedAtDesc(
                        userId, NotificationType.APPROVAL_TASK, PageRequest.of(0, 50));
        return tasks.stream().map(this::toDto).collect(Collectors.toList());
    }

    // ============ 已读 ============

    /** 单条标记已读；不存在则返回 false */
    @Transactional
    public boolean markRead(Long userId, Long id) {
        return notificationRepository.markRead(id, userId) > 0;
    }

    /** 全部标记已读 */
    @Transactional
    public void markAllRead(Long userId) {
        notificationRepository.markAllRead(userId);
    }

    // ============ 映射 ============

    private NotificationDto toDto(Notification n) {
        NotificationDto dto = new NotificationDto();
        dto.setId(n.getId());
        dto.setType(n.getType());
        dto.setTypeLabel(typeLabel(n.getType()));
        dto.setTitle(n.getTitle());
        dto.setContent(n.getContent());
        dto.setRelatedType(n.getRelatedType());
        dto.setRelatedId(n.getRelatedId());
        dto.setLink(n.getLink());
        dto.setRead(n.getRead());
        dto.setCreatedAt(n.getCreatedAt());
        return dto;
    }

    private String typeLabel(NotificationType type) {
        if (type == null) return "";
        switch (type) {
            case APPROVAL_TASK:        return "待办审批";
            case APPROVAL_RESULT:      return "审批结果";
            case CONFIDENTIALITY_GRANT: return "保密授权";
            case CATEGORY_GRANT:       return "分类授权";
            case DOCUMENT_SHARE:       return "文档分享";
            case SYSTEM_ANNOUNCEMENT:  return "系统公告";
            default:                   return type.name();
        }
    }
}
