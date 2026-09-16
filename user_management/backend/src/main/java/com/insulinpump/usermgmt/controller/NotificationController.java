package com.insulinpump.usermgmt.controller;

import com.insulinpump.usermgmt.dto.AnnouncementRequest;
import com.insulinpump.usermgmt.dto.ApiResponse;
import com.insulinpump.usermgmt.dto.NotificationDto;
import com.insulinpump.usermgmt.dto.NotificationStatsDto;
import com.insulinpump.usermgmt.model.NotificationType;
import com.insulinpump.usermgmt.model.User;
import com.insulinpump.usermgmt.service.NotificationService;
import org.springframework.data.domain.Page;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

import java.util.List;

/**
 * 站内通知 Controller
 *
 * 权限矩阵（均需登录）：
 *  - GET   /api/notifications                 当前用户通知分页列表
 *  - GET   /api/notifications/stats           顶栏角标（未读 + 待办数）
 *  - GET   /api/notifications/todos           审批待办列表
 *  - PUT   /api/notifications/{id}/read       单条标记已读
 *  - PUT   /api/notifications/read-all        全部标记已读
 *  - POST  /api/notifications/announcement    系统公告（ADMIN）
 */
@RestController
@RequestMapping("/api/notifications")
public class NotificationController {

    private final NotificationService notificationService;

    public NotificationController(NotificationService notificationService) {
        this.notificationService = notificationService;
    }

    /** 当前用户通知分页列表（新 -> 旧） */
    @GetMapping
    public ResponseEntity<ApiResponse<Page<NotificationDto>>> list(
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size,
            @AuthenticationPrincipal User currentUser) {
        Page<NotificationDto> result = notificationService.list(currentUser.getId(), page, size);
        return ResponseEntity.ok(ApiResponse.success(result));
    }

    /** 顶栏角标：未读总数 + 审批待办数 */
    @GetMapping("/stats")
    public ResponseEntity<ApiResponse<NotificationStatsDto>> stats(
            @AuthenticationPrincipal User currentUser) {
        NotificationStatsDto stats = notificationService.stats(currentUser.getId());
        return ResponseEntity.ok(ApiResponse.success(stats));
    }

    /** 审批待办列表（未读的 APPROVAL_TASK） */
    @GetMapping("/todos")
    public ResponseEntity<ApiResponse<List<NotificationDto>>> todos(
            @AuthenticationPrincipal User currentUser) {
        List<NotificationDto> todos = notificationService.todos(currentUser.getId());
        return ResponseEntity.ok(ApiResponse.success(todos));
    }

    /** 单条标记已读 */
    @PutMapping("/{id}/read")
    public ResponseEntity<ApiResponse<Void>> markRead(
            @PathVariable Long id,
            @AuthenticationPrincipal User currentUser) {
        boolean marked = notificationService.markRead(currentUser.getId(), id);
        if (!marked) {
            return ResponseEntity.ok(ApiResponse.error(404, "通知不存在"));
        }
        return ResponseEntity.ok(ApiResponse.success("已标记为已读", null));
    }

    /** 全部标记已读 */
    @PutMapping("/read-all")
    public ResponseEntity<ApiResponse<Void>> markAllRead(
            @AuthenticationPrincipal User currentUser) {
        notificationService.markAllRead(currentUser.getId());
        return ResponseEntity.ok(ApiResponse.success("已全部标记为已读", null));
    }

    /**
     * 发布系统公告（广播给所有启用用户）
     * 权限：ADMIN（notification:publish）
     */
    @PostMapping("/announcement")
    @PreAuthorize("hasAuthority('notification:publish')")
    public ResponseEntity<ApiResponse<Integer>> publishAnnouncement(
            @RequestBody AnnouncementRequest req,
            @AuthenticationPrincipal User currentUser) {
        if (req.getTitle() == null || req.getTitle().isBlank()) {
            throw new IllegalArgumentException("公告标题不能为空");
        }
        if (req.getContent() == null || req.getContent().isBlank()) {
            throw new IllegalArgumentException("公告内容不能为空");
        }
        int count = notificationService.broadcast(
                NotificationType.SYSTEM_ANNOUNCEMENT,
                req.getTitle().trim(),
                req.getContent().trim(),
                null, null, null);
        return ResponseEntity.ok(ApiResponse.success("公告已发布", count));
    }
}
