package com.insulinpump.usermgmt.controller;

import com.insulinpump.usermgmt.dto.ApiResponse;
import com.insulinpump.usermgmt.dto.CategoryAccessDto;
import com.insulinpump.usermgmt.dto.CategoryAccessRequest;
import com.insulinpump.usermgmt.model.AccessMode;
import com.insulinpump.usermgmt.model.DocumentCategory;
import com.insulinpump.usermgmt.model.DocumentType;
import com.insulinpump.usermgmt.model.User;
import com.insulinpump.usermgmt.model.UserCategoryAccess;
import com.insulinpump.usermgmt.repository.DocumentCategoryRepository;
import com.insulinpump.usermgmt.repository.UserCategoryAccessRepository;
import com.insulinpump.usermgmt.repository.UserRepository;
import com.insulinpump.usermgmt.model.NotificationType;
import com.insulinpump.usermgmt.service.NotificationService;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

/**
 * 用户资料分类授权 Controller
 *
 * 管理员可给任意员工分配"可访问某 RESEARCH 资料分类"权限（用户级，独立于角色）。
 * 与保密等级授权（ConfidentialityAccessController）OR 组合：任一命中即可见（TOP_SECRET 除外）。
 *
 * 权限矩阵：
 *  - PUT    /api/users/{id}/category-access               ADMIN（user:assign-category）批量授予
 *  - GET    /api/users/{id}/category-access               ADMIN 或本人查询自己的授权
 *  - DELETE /api/users/{id}/category-access/{categoryId}  ADMIN（user:assign-category）撤销单个
 *
 * 校验：
 *  - 仅 RESEARCH 分类可授权；SYSTEM 分类整批拒绝（不部分写入）
 *  - 幂等：已存在的跳过，不报错
 */
@RestController
@RequestMapping("/api/users/{userId}/category-access")
public class CategoryAccessController {

    private final UserCategoryAccessRepository accessRepository;
    private final UserRepository userRepository;
    private final DocumentCategoryRepository categoryRepository;
    private final NotificationService notificationService;

    public CategoryAccessController(UserCategoryAccessRepository accessRepository,
                                     UserRepository userRepository,
                                     DocumentCategoryRepository categoryRepository,
                                     NotificationService notificationService) {
        this.accessRepository = accessRepository;
        this.userRepository = userRepository;
        this.categoryRepository = categoryRepository;
        this.notificationService = notificationService;
    }

    /**
     * 查询某用户的全部资料分类授权
     * 权限：ADMIN 或本人查询自己
     */
    @GetMapping
    public ResponseEntity<ApiResponse<List<CategoryAccessDto>>> list(
            @PathVariable Long userId,
            @AuthenticationPrincipal User currentUser) {
        if (!isAdmin(currentUser) && !userId.equals(currentUser.getId())) {
            throw new SecurityException("无权查询他人的资料分类授权");
        }
        userRepository.findById(userId)
                .orElseThrow(() -> new IllegalArgumentException("用户不存在"));

        List<UserCategoryAccess> accesses = accessRepository.findByUserId(userId);
        List<CategoryAccessDto> dtos = accesses.stream()
                .map(a -> toDto(a, userId))
                .collect(Collectors.toList());
        return ResponseEntity.ok(ApiResponse.success(dtos));
    }

    /**
     * 批量授予资料分类访问权限（幂等：已存在的跳过）
     * 权限：ADMIN（user:assign-category）
     *
     * 校验：
     *  - categoryIds 非空
     *  - 所有分类必须存在且为 RESEARCH 类型（SYSTEM 分类整批拒绝）
     *  - 已存在的授权跳过
     *
     * 返回：该用户当前所有授权（含本次新增 + 原有）
     */
    @PutMapping
    @PreAuthorize("hasAuthority('user:assign-category')")
    public ResponseEntity<ApiResponse<List<CategoryAccessDto>>> grant(
            @PathVariable Long userId,
            @RequestBody CategoryAccessRequest req,
            @AuthenticationPrincipal User currentUser) {
        User target = userRepository.findById(userId)
                .orElseThrow(() -> new IllegalArgumentException("用户不存在"));

        if (req.getCategoryIds() == null || req.getCategoryIds().isEmpty()) {
            throw new IllegalArgumentException("分类 ID 列表不能为空");
        }

        // 去重
        Set<Long> requestedIds = new HashSet<>(req.getCategoryIds());

        // 一次性查询所有分类，校验存在性 + RESEARCH 类型
        List<DocumentCategory> categories = categoryRepository.findAllById(requestedIds);
        if (categories.size() != requestedIds.size()) {
            throw new IllegalArgumentException("部分分类不存在");
        }
        for (DocumentCategory cat : categories) {
            if (cat.getDocType() != DocumentType.RESEARCH) {
                throw new IllegalArgumentException(
                        "仅可授权 RESEARCH 资料分类，分类 " + cat.getName()
                                + " (" + cat.getCode() + ") 为 SYSTEM 类型");
            }
        }

        AccessMode mode = parseAccessMode(req.getAccessMode());
        AccessMode effectiveMode = mode != null ? mode : AccessMode.READ_ONLY;

        // 一次性加载该用户已有授权，按分类 ID 建索引，避免循环内重复查询
        List<UserCategoryAccess> existingAccesses = accessRepository.findByUserId(userId);
        Map<Long, UserCategoryAccess> existingByCatId = existingAccesses.stream()
                .filter(a -> a.getCategory() != null)
                .collect(Collectors.toMap(a -> a.getCategory().getId(), a -> a, (a, b) -> a));

        // 幂等写入：已存在的更新读写模式（仅当请求携带 accessMode），不存在的按 effectiveMode 新建
        int grantedCount = 0;
        for (DocumentCategory cat : categories) {
            UserCategoryAccess existing = existingByCatId.get(cat.getId());
            if (existing != null) {
                if (mode != null && existing.getAccessMode() != effectiveMode) {
                    existing.setAccessMode(effectiveMode);
                    accessRepository.save(existing);
                }
            } else {
                accessRepository.save(new UserCategoryAccess(target, cat, currentUser, effectiveMode));
                grantedCount++;
            }
        }

        // 通知被授权员工（仅当有新增授权时）
        if (grantedCount > 0) {
            notificationService.create(
                    userId,
                    NotificationType.CATEGORY_GRANT,
                    "分类授权",
                    "管理员授予您 " + grantedCount + " 个研发资料分类的数据访问权限（"
                            + modeLabel(effectiveMode) + "）",
                    "USER", userId, "/employees");
        }

        // 返回该用户当前所有授权
        List<UserCategoryAccess> all = accessRepository.findByUserId(userId);
        List<CategoryAccessDto> dtos = all.stream()
                .map(a -> toDto(a, userId))
                .collect(Collectors.toList());
        return ResponseEntity.ok(ApiResponse.success("授权成功", dtos));
    }

    /**
     * 撤销某用户的某个资料分类授权
     * 权限：ADMIN（user:assign-category）
     */
    @DeleteMapping("/{categoryId}")
    @PreAuthorize("hasAuthority('user:assign-category')")
    public ResponseEntity<ApiResponse<Void>> revoke(
            @PathVariable Long userId,
            @PathVariable Long categoryId,
            @AuthenticationPrincipal User currentUser) {
        userRepository.findById(userId)
                .orElseThrow(() -> new IllegalArgumentException("用户不存在"));

        accessRepository.deleteByUserIdAndCategoryId(userId, categoryId);
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

    private CategoryAccessDto toDto(UserCategoryAccess access, Long userId) {
        CategoryAccessDto dto = new CategoryAccessDto();
        dto.setId(access.getId());
        dto.setUserId(userId);
        dto.setUserName(access.getUser() != null ? access.getUser().getRealName() : null);
        dto.setCategoryId(access.getCategory() != null ? access.getCategory().getId() : null);
        dto.setCategoryName(access.getCategory() != null ? access.getCategory().getName() : null);
        dto.setCategoryCode(access.getCategory() != null ? access.getCategory().getCode() : null);
        dto.setAccessMode(access.getAccessMode() != null ? access.getAccessMode().name() : "READ_ONLY");
        dto.setGrantedById(access.getGrantedBy() != null ? access.getGrantedBy().getId() : null);
        dto.setGrantedByName(access.getGrantedBy() != null ? access.getGrantedBy().getRealName() : null);
        dto.setGrantedAt(access.getGrantedAt());
        return dto;
    }
}
