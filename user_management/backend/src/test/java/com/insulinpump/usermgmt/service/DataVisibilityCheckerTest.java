package com.insulinpump.usermgmt.service;

import com.insulinpump.usermgmt.model.*;
import jakarta.persistence.criteria.CriteriaBuilder;
import jakarta.persistence.criteria.CriteriaQuery;
import jakarta.persistence.criteria.Predicate;
import jakarta.persistence.criteria.Root;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;

import java.util.HashSet;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

/**
 * DataVisibilityChecker 单元测试
 *
 * 覆盖核心场景：
 *   1. ADMIN 全见（含 TOP_SECRET）
 *   2. owner 自己全见（含 TOP_SECRET）
 *   3. 同部门员工可访问本部门他人全部等级数据（所有员工，不限于部门负责人）
 *   4. 员工不可访问其他部门数据（无 allowedLevels 授权时）
 *   5. 部门负责人跨部门也需 allowedLevels 授权（不再是默认可见）
 *   6. 普通员工 allowedLevels 包含目标等级 = 可见（跨部门授权场景）
 *   7. 普通员工 allowedLevels 不含目标等级 = 不可见
 *   8. buildVisibilityPredicate: ADMIN 返回 conjunction
 *   9. resolveView: 非 ADMIN 请求 all 降级为 mine
 *
 * Category grant 扩展（5-arg canAccess / 5-arg buildVisibilityPredicate）：
 *  10. category grant 命中可见（跨部门、非 TOP_SECRET、有 category grant）
 *  11. category grant 不命中不可见（跨部门、有 category grant 但 category 不匹配）
 *  12. TOP_SECRET 即使有 category grant 也不可见
 *  13. 空 category（null）走默认规则（category grant 不命中）
 *  14. 同部门不需要 category grant（无 category grant 也可见）
 *  15. buildVisibilityPredicate 5-arg: 非 ADMIN + 有 category grant 时构造 category 谓词
 */
class DataVisibilityCheckerTest {

    private DataVisibilityChecker checker;

    private User admin;
    private User leader1;
    private User leader2;
    private User member1;
    private User member2;
    private Department dept1;
    private Department dept2;

    private DocumentCategory factoryProcessCat;
    private DocumentCategory testDataCat;

    @BeforeEach
    void setUp() {
        checker = new DataVisibilityChecker();

        Role adminRole = new Role("管理员", "ADMIN", "");
        Role engrRole = new Role("结构工程师", "STRUCTURAL_ENGINEER", "");

        dept1 = new Department("研发中心", "", null);
        dept1.setId(1L);
        dept2 = new Department("质量部", "", null);
        dept2.setId(2L);

        admin = createUser(1L, "admin", adminRole, dept1, false);

        leader1 = createUser(2L, "leader1", engrRole, dept1, true);
        leader2 = createUser(3L, "leader2", engrRole, dept2, true);

        member1 = createUser(4L, "member1", engrRole, dept1, false);
        member2 = createUser(5L, "member2", engrRole, dept2, false);

        factoryProcessCat = new DocumentCategory("FACTORY_PROCESS", "工厂工艺原理", "", 1, DocumentType.RESEARCH);
        factoryProcessCat.setId(10L);
        testDataCat = new DocumentCategory("TEST_DATA", "测试数据", "", 2, DocumentType.RESEARCH);
        testDataCat.setId(11L);
    }

    // ============ canAccess 测试 ============

    @Nested
    @DisplayName("canAccess() 业务可见性判定")
    class CanAccessTests {

        @Test
        @DisplayName("1. ADMIN 可访问所有保密等级（含 TOP_SECRET）")
        void adminCanAccessAllLevels() {
            for (ConfidentialityLevel level : ConfidentialityLevel.values()) {
                assertTrue(checker.canAccess(admin, member2, level),
                        "ADMIN 应可访问 " + level);
            }
        }

        @Test
        @DisplayName("2. owner 可访问自己所有等级的数据（含 TOP_SECRET）")
        void ownerCanAccessOwnData() {
            for (ConfidentialityLevel level : ConfidentialityLevel.values()) {
                assertTrue(checker.canAccess(member1, member1, level),
                        "Owner 应可访问自己的 " + level);
            }
        }

        @Test
        @DisplayName("3. 同部门员工可访问本部门他人全部等级数据（不限于部门负责人）")
        void sameDeptMemberCanAccessSameDeptAllLevels() {
            // member1 和 leader1 都在 dept1，member1 不是 leader 但应可见本部门
            for (ConfidentialityLevel level : ConfidentialityLevel.values()) {
                assertTrue(checker.canAccess(member1, leader1, level),
                        "同部门员工应可访问本部门 " + level);
            }
        }

        @Test
        @DisplayName("4. 员工不可访问其他部门数据（无 allowedLevels 授权时）")
        void memberCannotAccessOtherDeptWithoutGrant() {
            // member1 在 dept1, member2 在 dept2，member1 无授权
            for (ConfidentialityLevel level : ConfidentialityLevel.values()) {
                assertFalse(checker.canAccess(member1, member2, level),
                        "无授权员工不应可见其他部门 " + level);
            }
        }

        @Test
        @DisplayName("5. 部门负责人跨部门也需 allowedLevels 授权")
        void deptLeaderCrossDeptRequiresAllowedLevels() {
            // leader1 在 dept1, member2 在 dept2：负责人跨部门同样不可见
            for (ConfidentialityLevel level : ConfidentialityLevel.values()) {
                assertFalse(checker.canAccess(leader1, member2, level),
                        "部门负责人跨部门不应可见 " + level);
            }
        }

        @Test
        @DisplayName("6. 普通员工 allowedLevels 含目标等级 = 可见（跨部门授权）")
        void regularUserWithAllowedLevelCanAccess() {
            Set<UserConfidentialityAccess> grants = new HashSet<>();
            grants.add(new UserConfidentialityAccess(member1, ConfidentialityLevel.CONFIDENTIAL, admin));
            grants.add(new UserConfidentialityAccess(member1, ConfidentialityLevel.TOP_SECRET, admin));
            member1.setConfidentialityAccesses(grants);

            assertTrue(checker.canAccess(member1, member2, ConfidentialityLevel.CONFIDENTIAL));
            assertTrue(checker.canAccess(member1, member2, ConfidentialityLevel.TOP_SECRET));
        }

        @Test
        @DisplayName("7. 普通员工 allowedLevels 不含目标等级 = 不可见（跨部门场景）")
        void regularUserWithoutAllowedLevelCannotAccess() {
            Set<UserConfidentialityAccess> grants = new HashSet<>();
            grants.add(new UserConfidentialityAccess(member1, ConfidentialityLevel.PUBLIC, admin));
            member1.setConfidentialityAccesses(grants);

            // 有 PUBLIC 授权，但无 INTERNAL/CONFIDENTIAL/TOP_SECRET（跨部门 member2）
            assertTrue(checker.canAccess(member1, member2, ConfidentialityLevel.PUBLIC));
            assertFalse(checker.canAccess(member1, member2, ConfidentialityLevel.INTERNAL));
            assertFalse(checker.canAccess(member1, member2, ConfidentialityLevel.CONFIDENTIAL));
            assertFalse(checker.canAccess(member1, member2, ConfidentialityLevel.TOP_SECRET));
        }
    }

    // ============ buildVisibilityPredicate 测试 ============

    @Nested
    @DisplayName("buildVisibilityPredicate() JPA Specification 构造")
    class BuildPredicateTests {

        @Test
        @DisplayName("8. ADMIN 返回 conjunction（不加条件 = 全见）")
        void adminReturnsConjunction() {
            Root<?> root = mock(Root.class);
            CriteriaQuery<?> query = mock(CriteriaQuery.class);
            CriteriaBuilder cb = mock(CriteriaBuilder.class);
            Predicate conjunction = mock(Predicate.class);
            when(cb.conjunction()).thenReturn(conjunction);

            Predicate result = checker.buildVisibilityPredicate(root, query, cb, admin);

            assertSame(conjunction, result);
            verify(cb).conjunction();
            // 不应访问 root 或构造任何字段条件
            verifyNoInteractions(root);
        }
    }

    // ============ resolveView 测试 ============

    @Nested
    @DisplayName("resolveView() 视图参数解析")
    class ResolveViewTests {

        @Test
        @DisplayName("9a. 非 ADMIN 请求 all 降级为 mine")
        void nonAdminAllDowngradedToMine() {
            assertEquals("mine", checker.resolveView("all", member1));
        }

        @Test
        @DisplayName("9b. ADMIN 请求 all 保持 all")
        void adminAllStaysAll() {
            assertEquals("all", checker.resolveView("all", admin));
        }

        @Test
        @DisplayName("9c. 空/blank 视图返回空字符串（触发默认规则）")
        void blankViewReturnsEmpty() {
            assertEquals("", checker.resolveView(null, member1));
            assertEquals("", checker.resolveView("", member1));
            assertEquals("", checker.resolveView("  ", member1));
        }

        @Test
        @DisplayName("9d. mine/shared/public 原样返回")
        void namedViewsPassedThrough() {
            assertEquals("mine", checker.resolveView("mine", member1));
            assertEquals("public", checker.resolveView("public", member1));
            assertEquals("shared", checker.resolveView("shared", member1));
        }
    }

    // ============ canAccess 5-arg（category grant）测试 ============

    @Nested
    @DisplayName("canAccess() 5-arg category grant 判定")
    class CategoryGrantTests {

        @Test
        @DisplayName("10. category grant 命中可见（跨部门、非 TOP_SECRET、有 category grant）")
        void categoryGrantHitCanAccess() {
            // member1 在 dept1，授权 factoryProcessCat；member2 在 dept2
            grantCategoryAccess(member1, factoryProcessCat, admin);

            // member2 的数据属于 factoryProcessCat，等级 INTERNAL（跨部门 + category 命中）
            assertTrue(checker.canAccess(member1, member2, ConfidentialityLevel.INTERNAL,
                    factoryProcessCat, true));
        }

        @Test
        @DisplayName("11. category grant 不命中不可见（跨部门、有 category grant 但 category 不匹配）")
        void categoryGrantMissCannotAccess() {
            // member1 仅授权 factoryProcessCat，目标数据属于 testDataCat
            grantCategoryAccess(member1, factoryProcessCat, admin);

            assertFalse(checker.canAccess(member1, member2, ConfidentialityLevel.INTERNAL,
                    testDataCat, true));
        }

        @Test
        @DisplayName("12. TOP_SECRET 即使有 category grant 也不可见")
        void topSecretNotReleasedByCategoryGrant() {
            // member1 有 factoryProcessCat 授权，但目标等级是 TOP_SECRET
            grantCategoryAccess(member1, factoryProcessCat, admin);

            assertFalse(checker.canAccess(member1, member2, ConfidentialityLevel.TOP_SECRET,
                    factoryProcessCat, true));
        }

        @Test
        @DisplayName("13. 空 category（null）走默认规则（category grant 不命中）")
        void nullCategoryFallsThroughToDefault() {
            grantCategoryAccess(member1, factoryProcessCat, admin);

            // category=null 时即使 includeCategoryGrant=true 也不应触发 category grant
            assertFalse(checker.canAccess(member1, member2, ConfidentialityLevel.INTERNAL,
                    null, true));
        }

        @Test
        @DisplayName("14. 同部门不需要 category grant（无 category grant 也可见）")
        void sameDeptDoesNotNeedCategoryGrant() {
            // member1 和 leader1 同在 dept1，member1 无任何授权
            // 跨部门场景不适用，此处验证同部门 + includeCategoryGrant=true 不破坏同部门可见
            assertTrue(checker.canAccess(member1, leader1, ConfidentialityLevel.TOP_SECRET,
                    factoryProcessCat, true));
        }

        @Test
        @DisplayName("15. buildVisibilityPredicate 5-arg: 非 ADMIN + 有 category grant 时构造 category 谓词")
        void buildPredicateWithCategoryGrant() {
            grantCategoryAccess(member1, factoryProcessCat, admin);

            Root<?> root = mock(Root.class);
            CriteriaQuery<?> query = mock(CriteriaQuery.class);
            CriteriaBuilder cb = mock(CriteriaBuilder.class);
            jakarta.persistence.criteria.Path<Object> ownerPath = mock(jakarta.persistence.criteria.Path.class);
            jakarta.persistence.criteria.Path<Object> deptPath = mock(jakarta.persistence.criteria.Path.class);
            jakarta.persistence.criteria.Path<Object> categoryPath = mock(jakarta.persistence.criteria.Path.class);
            jakarta.persistence.criteria.Path<Object> categoryIdPath = mock(jakarta.persistence.criteria.Path.class);
            jakarta.persistence.criteria.Path<Object> anyPath = mock(jakarta.persistence.criteria.Path.class);
            Predicate ownerEq = mock(Predicate.class);
            Predicate deptEq = mock(Predicate.class);
            Predicate levelIn = mock(Predicate.class);
            Predicate categoryIn = mock(Predicate.class);
            Predicate notTopSecret = mock(Predicate.class);
            Predicate categoryAnd = mock(Predicate.class);
            Predicate finalOr = mock(Predicate.class);

            when(root.get("owner")).thenReturn(ownerPath);
            when(ownerPath.get("id")).thenReturn(anyPath);
            when(ownerPath.get("department")).thenReturn(deptPath);
            when(deptPath.get("id")).thenReturn(anyPath);
            when(root.get("confidentialityLevel")).thenReturn(anyPath);
            // Path.in(Collection) 与 Path.in(Object...) 是不同重载，都 mock
            when(anyPath.in(any(java.util.Collection.class))).thenReturn(levelIn);
            when(root.get("category")).thenReturn(categoryPath);
            when(categoryPath.get("id")).thenReturn(categoryIdPath);
            when(categoryIdPath.in(any(java.util.Collection.class))).thenReturn(categoryIn);
            when(cb.equal(any(), any())).thenReturn(ownerEq);
            when(cb.notEqual(any(jakarta.persistence.criteria.Expression.class), any(Object.class)))
                    .thenReturn(notTopSecret);
            when(cb.and(any(Predicate.class), any(Predicate.class))).thenReturn(categoryAnd);
            when(cb.or(any(Predicate[].class))).thenReturn(finalOr);

            Predicate result = checker.buildVisibilityPredicate(root, query, cb, member1, true);

            assertSame(finalOr, result);
            // 验证 category 谓词被构造
            verify(root).get("category");
            verify(cb).and(categoryIn, notTopSecret);
        }

        @Test
        @DisplayName("15b. buildVisibilityPredicate 5-arg: 无 category grant 时与 4-arg 行为一致（不构造 category 谓词）")
        void buildPredicateWithoutCategoryGrantNoCategoryClause() {
            // member1 无 category grant
            Root<?> root = mock(Root.class);
            CriteriaQuery<?> query = mock(CriteriaQuery.class);
            CriteriaBuilder cb = mock(CriteriaBuilder.class);
            jakarta.persistence.criteria.Path<Object> ownerPath = mock(jakarta.persistence.criteria.Path.class);
            jakarta.persistence.criteria.Path<Object> deptPath = mock(jakarta.persistence.criteria.Path.class);
            jakarta.persistence.criteria.Path<Object> anyPath = mock(jakarta.persistence.criteria.Path.class);
            Predicate ownerEq = mock(Predicate.class);
            Predicate finalOr = mock(Predicate.class);

            when(root.get("owner")).thenReturn(ownerPath);
            when(ownerPath.get("id")).thenReturn(anyPath);
            when(ownerPath.get("department")).thenReturn(deptPath);
            when(deptPath.get("id")).thenReturn(anyPath);
            when(cb.equal(any(), any())).thenReturn(ownerEq);
            when(cb.or(any(Predicate[].class))).thenReturn(finalOr);

            checker.buildVisibilityPredicate(root, query, cb, member1, true);

            // 无 category grant 时不应访问 root.get("category")
            verify(root, never()).get("category");
        }
    }

    // ============ 辅助方法 ============

    private User createUser(Long id, String username, Role role, Department dept, boolean isLeader) {
        User u = new User();
        u.setId(id);
        u.setUsername(username);
        u.setRole(role);
        u.setDepartment(dept);
        u.setDepartmentLeader(isLeader);
        return u;
    }

    private void grantCategoryAccess(User user, DocumentCategory cat, User grantedBy) {
        Set<UserCategoryAccess> set = user.getCategoryAccesses();
        if (set == null) {
            set = new HashSet<>();
            user.setCategoryAccesses(set);
        }
        set.add(new UserCategoryAccess(user, cat, grantedBy));
    }
}
