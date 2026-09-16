package com.insulinpump.usermgmt.service;

import com.insulinpump.usermgmt.model.AccessMode;
import com.insulinpump.usermgmt.model.ConfidentialityLevel;
import com.insulinpump.usermgmt.model.DocumentCategory;
import com.insulinpump.usermgmt.model.User;
import com.insulinpump.usermgmt.model.UserCategoryAccess;
import com.insulinpump.usermgmt.model.UserConfidentialityAccess;
import jakarta.persistence.criteria.CriteriaBuilder;
import jakarta.persistence.criteria.CriteriaQuery;
import jakarta.persistence.criteria.Predicate;
import jakarta.persistence.criteria.Root;
import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

/**
 * 统一数据可见性判定组件
 *
 * 收敛 3 处 Service 重复的 isAdmin / checkVisibility 逻辑（DRY）。
 *
 * 可见性规则（按优先级短路）：
 *   1. ADMIN                          -> 全见
 *   2. owner == currentUser           -> 自己录入的全见（含 TOP_SECRET）
 *   3. owner.department == currentUser.department -> 同部门全见（含所有保密等级，所有员工）
 *   4. allowedLevels 命中保密等级      -> 跨部门授权可见（用户级授权，独立于角色）
 *   5. categoryAccesses 命中分类 && level != TOP_SECRET -> 跨部门按分类授权可见
 *
 * TOP_SECRET 隔离：categoryAccesses 不释放 TOP_SECRET；TOP_SECRET 必须由 allowedLevels=TOP_SECRET
 * 单独释放（避免分类授权意外泄露绝密资料）。
 *
 * 默认空授权集 = 普通员工只见自己 + 本部门他人数据（符合"同部门共享"需求）。
 * 跨部门访问必须由 ADMIN 显式授予 allowedLevels 或 categoryAccesses。
 *
 * 数据流：
 *   JwtAuthFilter 加载 User -> 计算 departmentLeader + EAGER 加载 confidentialityAccesses + categoryAccesses
 *                              ↓
 *   DataVisibilityChecker.canAccess / buildVisibilityPredicate
 *                              ↓
 *   Service.checkVisibility / Specification
 *
 * 不在职责内：
 *   - SHARED 策略（ResearchMaterial 的 DocumentShare）由 DocumentService 内部处理
 *   - 体系文档的 DocumentVisibility 模型不动（参见开发计划 NOT in scope）
 */
@Component
public class DataVisibilityChecker {

    /**
     * 是否为系统管理员
     */
    public boolean isAdmin(User user) {
        return user != null
                && user.getRole() != null
                && "ADMIN".equals(user.getRole().getCode());
    }

    /**
     * 是否为某部门负责人
     *
     * 依赖 JwtAuthFilter 在加载 User 时计算的 @Transient departmentLeader 字段。
     * 计算逻辑：user.department.leader.id == user.id
     */
    public boolean isDeptLeader(User user) {
        return user != null && Boolean.TRUE.equals(user.getDepartmentLeader());
    }

    /**
     * 获取用户被授权的保密等级集（用户级，独立于角色）
     *
     * 默认空集。授权通过 PUT /api/users/{id}/confidentiality-access 管理。
     */
    public Set<ConfidentialityLevel> getAllowedLevels(User user) {
        if (user == null || user.getConfidentialityAccesses() == null
                || user.getConfidentialityAccesses().isEmpty()) {
            return Set.of();
        }
        return user.getConfidentialityAccesses().stream()
                .map(UserConfidentialityAccess::getConfidentialityLevel)
                .collect(Collectors.toSet());
    }

    /**
     * 获取用户被授权的资料分类 ID 集（用户级，独立于角色）
     *
     * 默认空集。授权通过 PUT /api/users/{id}/category-access 管理。
     */
    public Set<Long> getAllowedCategoryIds(User user) {
        if (user == null || user.getCategoryAccesses() == null
                || user.getCategoryAccesses().isEmpty()) {
            return Set.of();
        }
        return user.getCategoryAccesses().stream()
                .map(a -> a.getCategory() != null ? a.getCategory().getId() : null)
                .filter(id -> id != null)
                .collect(Collectors.toSet());
    }

    /**
     * 业务可见性判定（不涉及 JPA）- 不带 category 参数
     *
     * 等价于 canAccess(user, owner, level, null, false)。
     * 保留向后兼容（CommercialRecordService 无 category 字段，仍用此重载）。
     */
    public boolean canAccess(User user, User owner, ConfidentialityLevel level) {
        return canAccess(user, owner, level, null, false);
    }

    /**
     * 业务可见性判定（不涉及 JPA）- 带 category 参数
     *
     * @param user                 当前用户
     * @param owner                数据所有者
     * @param level                数据保密等级
     * @param category             数据所属分类（可为 null：无分类字段时）
     * @param includeCategoryGrant 是否启用 category grant 检查（实体有 category 字段时传 true）
     * @return true 可访问 / false 拒绝
     */
    public boolean canAccess(User user, User owner, ConfidentialityLevel level,
                              DocumentCategory category, boolean includeCategoryGrant) {
        if (user == null) {
            return false;
        }
        // 1. ADMIN 全见
        if (isAdmin(user)) {
            return true;
        }
        // 2. owner 自己全见
        if (owner != null && owner.getId().equals(user.getId())) {
            return true;
        }
        // 3. 同部门全见（所有员工，不限于部门负责人）
        if (owner != null
                && owner.getDepartment() != null
                && user.getDepartment() != null
                && owner.getDepartment().getId().equals(user.getDepartment().getId())) {
            return true;
        }
        // 4. 用户被授权的保密等级（跨部门授权）
        if (getAllowedLevels(user).contains(level)) {
            return true;
        }
        // 5. category grant：跨部门按分类授权（仅非 TOP_SECRET）
        if (includeCategoryGrant
                && category != null
                && level != ConfidentialityLevel.TOP_SECRET
                && getAllowedCategoryIds(user).contains(category.getId())) {
            return true;
        }
        return false;
    }

    /**
     * JPA Specification 可见性 Predicate 构造 - 不带 category grant
     *
     * 等价于 buildVisibilityPredicate(root, query, cb, currentUser, false)。
     * 保留向后兼容（CommercialRecordService 无 category 字段，仍用此重载）。
     */
    public Predicate buildVisibilityPredicate(Root<?> root, CriteriaQuery<?> query,
                                               CriteriaBuilder cb, User currentUser) {
        return buildVisibilityPredicate(root, query, cb, currentUser, false);
    }

    /**
     * JPA Specification 可见性 Predicate 构造 - 可选 category grant
     *
     * 生成 SQL 条件：
     *   owner_id = ?currentUser
     *   OR owner_dept_id = ?currentUser.deptId           -- 同部门全见（所有员工）
     *   OR confidentiality_level IN (?currentUser.allowedLevels)  -- 跨部门等级授权
     *   [OR (category_id IN (?currentUser.allowedCategoryIds) AND confidentiality_level != TOP_SECRET)] -- 跨部门分类授权
     *
     * ADMIN: 返回 conjunction()（即 1=1，不加任何条件，全见）。
     *
     * @param includeCategoryGrant true 时追加 category grant 谓词（仅对有 category 字段的实体）
     */
    public Predicate buildVisibilityPredicate(Root<?> root, CriteriaQuery<?> query,
                                               CriteriaBuilder cb, User currentUser,
                                               boolean includeCategoryGrant) {
        if (isAdmin(currentUser)) {
            // ADMIN 全见：不加条件
            return cb.conjunction();
        }

        List<Predicate> orPredicates = new ArrayList<>();

        // 1. owner = currentUser
        orPredicates.add(cb.equal(root.get("owner").get("id"), currentUser.getId()));

        // 2. 同部门全见（所有员工，不限于部门负责人）：owner.department.id = currentUser.department.id
        if (currentUser.getDepartment() != null) {
            orPredicates.add(cb.equal(
                    root.get("owner").get("department").get("id"),
                    currentUser.getDepartment().getId()));
        }

        // 3. 跨部门等级授权：用户被授权的保密等级
        Set<ConfidentialityLevel> levels = getAllowedLevels(currentUser);
        if (!levels.isEmpty()) {
            orPredicates.add(root.get("confidentialityLevel").in(levels));
        }

        // 4. 跨部门分类授权：category_id IN (allowedCategoryIds) AND level != TOP_SECRET
        if (includeCategoryGrant) {
            Set<Long> categoryIds = getAllowedCategoryIds(currentUser);
            if (!categoryIds.isEmpty()) {
                Predicate categoryIn = root.get("category").get("id").in(categoryIds);
                Predicate notTopSecret = cb.notEqual(
                        root.get("confidentialityLevel"), ConfidentialityLevel.TOP_SECRET);
                orPredicates.add(cb.and(categoryIn, notTopSecret));
            }
        }

        // 如果用户既无部门也无授权，等价于 "owner = currentUser"
        // 由 cb.or 单独处理时，PostgreSQL 会优化为简单条件
        return cb.or(orPredicates.toArray(new Predicate[0]));
    }

    /**
     * 是否被授予某保密等级的"可读写"（READ_WRITE）权限
     *
     * 仅 READ_WRITE 授权放行；READ_ONLY / 历史 NULL 均按只读处理（不释放写权限）。
     */
    public boolean hasWriteLevel(User user, ConfidentialityLevel level) {
        if (user == null || level == null || user.getConfidentialityAccesses() == null) {
            return false;
        }
        return user.getConfidentialityAccesses().stream()
                .anyMatch(a -> a.getConfidentialityLevel() == level
                        && a.getAccessMode() == AccessMode.READ_WRITE);
    }

    /**
     * 是否被授予某资料分类的"可读写"（READ_WRITE）权限
     *
     * 仅 READ_WRITE 授权放行；READ_ONLY / 历史 NULL 均按只读处理。
     */
    public boolean hasWriteCategory(User user, Long categoryId) {
        if (user == null || categoryId == null || user.getCategoryAccesses() == null) {
            return false;
        }
        return user.getCategoryAccesses().stream()
                .anyMatch(a -> a.getCategory() != null
                        && a.getCategory().getId().equals(categoryId)
                        && a.getAccessMode() == AccessMode.READ_WRITE);
    }

    /**
     * 修改/删除权限判定（写操作专用，区别于 canAccess 的读可见性）
     *
     * 规则（按优先级短路）：
     *   1. ADMIN                            -> 可修改/删除一切
     *   2. owner == currentUser             -> 可修改/删除自己的数据
     *   3. 被授予该保密等级 READ_WRITE       -> 可修改/删除该等级他人的数据（用户级授权）
     *   4. 被授予该分类 READ_WRITE（非 TOP_SECRET）-> 可修改/删除该分类他人的数据
     *
     * 刻意不含"同部门"条款：写权限比读权限更严格，
     * 同部门仅放开"查看"，修改他人数据必须靠 READ_WRITE 授权（或 ADMIN）。
     * 创建不受此限制（任何认证用户均可录入自己的数据）。
     *
     * @param user                 当前用户
     * @param owner                数据所有者
     * @param level                数据保密等级
     * @param category             数据所属分类（可为 null：无分类字段时）
     * @param includeCategoryGrant 是否启用 category 写授权检查（实体有 category 字段时传 true）
     * @return true 允许修改/删除 / false 拒绝
     */
    public boolean canModify(User user, User owner, ConfidentialityLevel level,
                             DocumentCategory category, boolean includeCategoryGrant) {
        if (user == null) {
            return false;
        }
        // 1. ADMIN 全权
        if (isAdmin(user)) {
            return true;
        }
        // 2. owner 自己
        if (owner != null && owner.getId().equals(user.getId())) {
            return true;
        }
        // 3. 该保密等级 READ_WRITE 授权（跨部门）
        if (hasWriteLevel(user, level)) {
            return true;
        }
        // 4. 该分类 READ_WRITE 授权（跨部门，仅非 TOP_SECRET，与读规则保持一致）
        if (includeCategoryGrant
                && category != null
                && level != ConfidentialityLevel.TOP_SECRET
                && hasWriteCategory(user, category.getId())) {
            return true;
        }
        return false;
    }

    /**
     * 解析 view 参数
     *
     * "mine"   -> owner = currentUser
     * "all"    -> ADMIN 全见；非 ADMIN 降级为 mine
     * "public" -> confidentialityLevel = PUBLIC
     * "shared" -> DocumentShare 表（仅 ResearchMaterial 用，DocumentService 内部处理）
     *
     * 返回 null 表示使用默认可见性规则（buildVisibilityPredicate）。
     */
    public String resolveView(String view, User currentUser) {
        String v = (view == null || view.isBlank()) ? "" : view.toLowerCase();
        if ("all".equals(v) && !isAdmin(currentUser)) {
            return "mine"; // 非 ADMIN 降级
        }
        return v;
    }
}
