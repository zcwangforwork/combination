package com.insulinpump.usermgmt.controller;

import com.insulinpump.usermgmt.dto.ApiResponse;
import com.insulinpump.usermgmt.dto.ConfidentialityAccessDto;
import com.insulinpump.usermgmt.dto.ConfidentialityAccessRequest;
import com.insulinpump.usermgmt.model.AccessMode;
import com.insulinpump.usermgmt.model.ConfidentialityLevel;
import com.insulinpump.usermgmt.model.User;
import com.insulinpump.usermgmt.model.UserConfidentialityAccess;
import com.insulinpump.usermgmt.repository.UserConfidentialityAccessRepository;
import com.insulinpump.usermgmt.repository.UserRepository;
import com.insulinpump.usermgmt.model.NotificationType;
import com.insulinpump.usermgmt.service.NotificationService;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.stream.Collectors;

/**
 * 用户保密等级授权 Controller
 *
 * 管理员可给任意员工分配"可访问保密等级"权限（用户级，独立于角色）。
 * 默认空集 = 普通员工只见自己录入的数据。授权后可见对应等级的他人数据。
 *
 * 权限矩阵：
 *  - PUT    /api/users/{id}/confidentiality-access  ADMIN（user:assign-confidentiality）
 *  - GET    /api/users/{id}/confidentiality-access  ADMIN 或本人查询自己的授权
 *  - DELETE /api/users/{id}/confidentiality-access  ADMIN（user:assign-confidentiality）
 */
@RestController
@RequestMapping("/api/users/{userId}/confidentiality-access")
public class ConfidentialityAccessController {

    private final UserConfidentialityAccessRepository accessRepository;
    private final UserRepository userRepository;
    private final NotificationService notificationService;

    public ConfidentialityAccessController(UserConfidentialityAccessRepository accessRepository,
                                            UserRepository userRepository,
                                            NotificationService notificationService) {
        this.accessRepository = accessRepository;
        this.userRepository = userRepository;
        this.notificationService = notificationService;
    }

    /**
     * 查询某用户的全部保密等级授权
     * 权限：ADMIN 或本人查询自己
     */
    @GetMapping
    public ResponseEntity<ApiResponse<List<ConfidentialityAccessDto>>> list(
            @PathVariable Long userId,
            @AuthenticationPrincipal User currentUser) {
        if (!isAdmin(currentUser) && !userId.equals(currentUser.getId())) {
            throw new SecurityException("无权查询他人的保密等级授权");
        }
        userRepository.findById(userId)
                .orElseThrow(() -> new IllegalArgumentException("用户不存在"));

        List<UserConfidentialityAccess> accesses = accessRepository.findByUserId(userId);
        List<ConfidentialityAccessDto> dtos = accesses.stream()
                .map(a -> toDto(a, userId))
                .collect(Collectors.toList());
        return ResponseEntity.ok(ApiResponse.success(dtos));
    }

    /**
     * 授予或更新某用户某保密等级的访问权限
     * 权限：ADMIN（user:assign-confidentiality）
     *
     * 语义：
     *  - 该等级尚未授权：按 accessMode（默认 READ_ONLY）新建授权
     *  - 该等级已授权：若请求携带 accessMode 则更新读写模式（只读 &lt;-&gt; 可读写），否则保持现状
     */
    @PutMapping
    @PreAuthorize("hasAuthority('user:assign-confidentiality')")
    public ResponseEntity<ApiResponse<ConfidentialityAccessDto>> grant(
            @PathVariable Long userId,
            @RequestBody ConfidentialityAccessRequest req,
            @AuthenticationPrincipal User currentUser) {
        User target = userRepository.findById(userId)
                .orElseThrow(() -> new IllegalArgumentException("用户不存在"));

        if (req.getConfidentialityLevel() == null || req.getConfidentialityLevel().isBlank()) {
            throw new IllegalArgumentException("保密等级不能为空");
        }
        ConfidentialityLevel level;
        try {
            level = ConfidentialityLevel.valueOf(req.getConfidentialityLevel().toUpperCase());
        } catch (IllegalArgumentException e) {
            throw new IllegalArgumentException("无效的保密等级: " + req.getConfidentialityLevel()
                    + "，可选值: PUBLIC / INTERNAL / CONFIDENTIAL / TOP_SECRET");
        }
        AccessMode mode = parseAccessMode(req.getAccessMode());

        // 已存在：有 accessMode 则更新读写模式（幂等切换），否则保持现状
        if (accessRepository.existsByUserIdAndConfidentialityLevel(userId, level)) {
            List<UserConfidentialityAccess> existing = accessRepository.findByUserId(userId);
            UserConfidentialityAccess found = existing.stream()
                    .filter(a -> a.getConfidentialityLevel() == level)
                    .findFirst()
                    .orElseThrow();
            if (mode != null && found.getAccessMode() != mode) {
                found.setAccessMode(mode);
                accessRepository.save(found);
            }
            return ResponseEntity.ok(ApiResponse.success("已授权", toDto(found, userId)));
        }

        UserConfidentialityAccess access = new UserConfidentialityAccess(
                target, level, currentUser, mode != null ? mode : AccessMode.READ_ONLY);
        UserConfidentialityAccess saved = accessRepository.save(access);

        // 通知被授权员工
        notificationService.create(
                userId,
                NotificationType.CONFIDENTIALITY_GRANT,
                "保密授权",
                "管理员授予您 " + level.name() + " 保密等级的数据访问权限（"
                        + modeLabel(mode != null ? mode : AccessMode.READ_ONLY) + "）",
                "USER", userId, "/employees");

        return ResponseEntity.ok(ApiResponse.success("授权成功", toDto(saved, userId)));
    }

    /**
     * 撤销某用户的某保密等级访问权限
     * 权限：ADMIN（user:assign-confidentiality）
     */
    @DeleteMapping
    @PreAuthorize("hasAuthority('user:assign-confidentiality')")
    public ResponseEntity<ApiResponse<Void>> revoke(
            @PathVariable Long userId,
            @RequestParam String confidentialityLevel,
            @AuthenticationPrincipal User currentUser) {
        userRepository.findById(userId)
                .orElseThrow(() -> new IllegalArgumentException("用户不存在"));

        ConfidentialityLevel level;
        try {
            level = ConfidentialityLevel.valueOf(confidentialityLevel.toUpperCase());
        } catch (IllegalArgumentException e) {
            throw new IllegalArgumentException("无效的保密等级: " + confidentialityLevel);
        }

        accessRepository.deleteByUserIdAndConfidentialityLevel(userId, level);
        return ResponseEntity.ok(ApiResponse.success("撤销成功", null));
    }

    private boolean isAdmin(User user) {
        return user != null
                && user.getRole() != null
                && "ADMIN".equals(user.getRole().getCode());
    }

    /**
     * 解析 accessMode。null/空白 => 返回 null（由调用方决定默认 READ_ONLY）；
     * 非法值抛出 IllegalArgumentException。
     */
    private AccessMode parseAccessMode(String accessMode) {
        if (accessMode == null || accessMode.isBlank()) {
            return null;
        }
        try {
            return AccessMode.valueOf(accessMode.toUpperCase());
        } catch (IllegalArgumentException e) {
            throw new IllegalArgumentException("无效的访问模式: " + accessMode
                    + "，可选值: READ_ONLY / READ_WRITE");
        }
    }

    private String modeLabel(AccessMode mode) {
        return mode == AccessMode.READ_WRITE ? "可读写" : "只读";
    }

    private ConfidentialityAccessDto toDto(UserConfidentialityAccess access, Long userId) {
        ConfidentialityAccessDto dto = new ConfidentialityAccessDto();
        dto.setId(access.getId());
        dto.setUserId(userId);
        dto.setUserName(access.getUser() != null ? access.getUser().getRealName() : null);
        dto.setConfidentialityLevel(access.getConfidentialityLevel() != null
                ? access.getConfidentialityLevel().name() : null);
        dto.setAccessMode(access.getAccessMode() != null ? access.getAccessMode().name() : "READ_ONLY");
        dto.setGrantedById(access.getGrantedBy() != null ? access.getGrantedBy().getId() : null);
        dto.setGrantedByName(access.getGrantedBy() != null ? access.getGrantedBy().getRealName() : null);
        dto.setGrantedAt(access.getGrantedAt());
        return dto;
    }
}
