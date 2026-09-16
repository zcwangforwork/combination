package com.insulinpump.usermgmt.controller;

import com.insulinpump.usermgmt.dto.ApiResponse;
import com.insulinpump.usermgmt.model.AuditLog;
import com.insulinpump.usermgmt.repository.AuditLogRepository;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;

/**
 * 审计日志查询 Controller
 *
 * 权限：仅 ADMIN（用户决策 #4）
 *
 * 查询维度：
 *  - 全部（分页倒序）
 *  - 按用户
 *  - 按实体（entityType + entityId）
 *  - 按动作
 *  - 按结果（SUCCESS/FAILURE）
 */
@RestController
@RequestMapping("/api/audit-logs")
@PreAuthorize("hasRole('ADMIN')")
public class AuditLogController {

    private final AuditLogRepository auditLogRepository;

    public AuditLogController(AuditLogRepository auditLogRepository) {
        this.auditLogRepository = auditLogRepository;
    }

    /**
     * 全部审计日志（分页，按时间倒序）
     */
    @GetMapping
    public ResponseEntity<ApiResponse<Page<AuditLog>>> list(
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size) {
        PageRequest pr = PageRequest.of(page, size, Sort.by(Sort.Direction.DESC, "timestamp"));
        Page<AuditLog> logs = auditLogRepository.findAllByOrderByTimestampDesc(pr);
        return ResponseEntity.ok(ApiResponse.success(logs));
    }

    /**
     * 按用户查询
     */
    @GetMapping("/by-user/{userId}")
    public ResponseEntity<ApiResponse<Page<AuditLog>>> byUser(
            @PathVariable Long userId,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size) {
        PageRequest pr = PageRequest.of(page, size, Sort.by(Sort.Direction.DESC, "timestamp"));
        Page<AuditLog> logs = auditLogRepository.findByUserIdOrderByTimestampDesc(userId, pr);
        return ResponseEntity.ok(ApiResponse.success(logs));
    }

    /**
     * 按实体查询
     */
    @GetMapping("/by-entity")
    public ResponseEntity<ApiResponse<Page<AuditLog>>> byEntity(
            @RequestParam String entityType,
            @RequestParam Long entityId,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size) {
        PageRequest pr = PageRequest.of(page, size, Sort.by(Sort.Direction.DESC, "timestamp"));
        Page<AuditLog> logs = auditLogRepository
                .findByEntityTypeAndEntityIdOrderByTimestampDesc(entityType, entityId, pr);
        return ResponseEntity.ok(ApiResponse.success(logs));
    }

    /**
     * 按动作查询
     */
    @GetMapping("/by-action/{action}")
    public ResponseEntity<ApiResponse<Page<AuditLog>>> byAction(
            @PathVariable String action,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size) {
        PageRequest pr = PageRequest.of(page, size, Sort.by(Sort.Direction.DESC, "timestamp"));
        Page<AuditLog> logs = auditLogRepository.findByActionOrderByTimestampDesc(action, pr);
        return ResponseEntity.ok(ApiResponse.success(logs));
    }

    /**
     * 按结果查询（SUCCESS / FAILURE）
     */
    @GetMapping("/by-result/{result}")
    public ResponseEntity<ApiResponse<Page<AuditLog>>> byResult(
            @PathVariable String result,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size) {
        PageRequest pr = PageRequest.of(page, size, Sort.by(Sort.Direction.DESC, "timestamp"));
        Page<AuditLog> logs = auditLogRepository.findByResultOrderByTimestampDesc(result, pr);
        return ResponseEntity.ok(ApiResponse.success(logs));
    }
}
