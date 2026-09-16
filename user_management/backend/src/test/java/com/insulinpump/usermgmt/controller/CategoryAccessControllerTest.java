package com.insulinpump.usermgmt.controller;

import com.insulinpump.usermgmt.dto.ApiResponse;
import com.insulinpump.usermgmt.dto.CategoryAccessRequest;
import com.insulinpump.usermgmt.dto.CategoryAccessDto;
import com.insulinpump.usermgmt.model.DocumentCategory;
import com.insulinpump.usermgmt.model.DocumentType;
import com.insulinpump.usermgmt.model.Role;
import com.insulinpump.usermgmt.model.User;
import com.insulinpump.usermgmt.model.UserCategoryAccess;
import com.insulinpump.usermgmt.repository.DocumentCategoryRepository;
import com.insulinpump.usermgmt.repository.UserCategoryAccessRepository;
import com.insulinpump.usermgmt.repository.UserRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.mockito.junit.jupiter.MockitoSettings;
import org.mockito.quality.Strictness;
import org.springframework.http.ResponseEntity;

import java.util.List;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

/**
 * CategoryAccessController 单元测试
 *
 * 覆盖 6 个核心场景：
 *   1. ADMIN 批量授予 RESEARCH 分类成功
 *   2. ADMIN 批量授予时已存在的跳过（幂等）
 *   3. 非本人非 ADMIN 查询授权被拒绝
 *   4. ADMIN 撤销某个分类授权
 *   5. SYSTEM 分类整批拒绝（不写入）
 *   6. 空分类列表抛异常
 */
@ExtendWith(MockitoExtension.class)
@MockitoSettings(strictness = Strictness.LENIENT)
class CategoryAccessControllerTest {

    @Mock
    private UserCategoryAccessRepository accessRepository;

    @Mock
    private UserRepository userRepository;

    @Mock
    private DocumentCategoryRepository categoryRepository;

    @InjectMocks
    private CategoryAccessController controller;

    private User admin;
    private User targetUser;
    private User otherUser;

    private DocumentCategory researchCat1;
    private DocumentCategory researchCat2;
    private DocumentCategory systemCat;

    @BeforeEach
    void setUp() {
        Role adminRole = new Role("管理员", "ADMIN", "");
        Role engrRole = new Role("结构工程师", "STRUCTURAL_ENGINEER", "");

        admin = createUser(1L, "admin", adminRole);
        targetUser = createUser(2L, "zhangsan", engrRole);
        otherUser = createUser(3L, "lisi", engrRole);

        researchCat1 = new DocumentCategory("FACTORY_PROCESS", "工厂工艺原理", "", 1, DocumentType.RESEARCH);
        researchCat1.setId(10L);
        researchCat2 = new DocumentCategory("TEST_DATA", "测试数据", "", 2, DocumentType.RESEARCH);
        researchCat2.setId(11L);
        systemCat = new DocumentCategory("PROCEDURE", "程序文件", "", 1, DocumentType.SYSTEM);
        systemCat.setId(1L);
    }

    @Test
    @DisplayName("1. ADMIN 批量授予 RESEARCH 分类成功")
    void adminGrantNewCategoriesSuccess() {
        when(userRepository.findById(2L)).thenReturn(Optional.of(targetUser));
        when(categoryRepository.findAllById(any(java.util.Set.class)))
                .thenReturn(List.of(researchCat1, researchCat2));
        when(accessRepository.existsByUserIdAndCategoryId(2L, 10L)).thenReturn(false);
        when(accessRepository.existsByUserIdAndCategoryId(2L, 11L)).thenReturn(false);
        when(accessRepository.save(any(UserCategoryAccess.class)))
                .thenAnswer(inv -> inv.getArgument(0));
        when(accessRepository.findByUserId(2L))
                .thenReturn(List.of(
                        new UserCategoryAccess(targetUser, researchCat1, admin),
                        new UserCategoryAccess(targetUser, researchCat2, admin)));

        CategoryAccessRequest req = new CategoryAccessRequest();
        req.setCategoryIds(List.of(10L, 11L));

        ResponseEntity<ApiResponse<List<CategoryAccessDto>>> result =
                controller.grant(2L, req, admin);

        assertNotNull(result);
        assertEquals(200, result.getStatusCode().value());
        assertEquals(2, result.getBody().getData().size());
        verify(accessRepository, times(2)).save(any(UserCategoryAccess.class));
    }

    @Test
    @DisplayName("2. ADMIN 批量授予时已存在的跳过（幂等）")
    void adminGrantExistingCategoriesIdempotent() {
        when(userRepository.findById(2L)).thenReturn(Optional.of(targetUser));
        when(categoryRepository.findAllById(any(java.util.Set.class)))
                .thenReturn(List.of(researchCat1, researchCat2));
        // 10L 已存在，11L 不存在
        when(accessRepository.existsByUserIdAndCategoryId(2L, 10L)).thenReturn(true);
        when(accessRepository.existsByUserIdAndCategoryId(2L, 11L)).thenReturn(false);
        when(accessRepository.save(any(UserCategoryAccess.class)))
                .thenAnswer(inv -> inv.getArgument(0));
        when(accessRepository.findByUserId(2L))
                .thenReturn(List.of(new UserCategoryAccess(targetUser, researchCat1, admin)));

        CategoryAccessRequest req = new CategoryAccessRequest();
        req.setCategoryIds(List.of(10L, 11L));

        ResponseEntity<ApiResponse<List<CategoryAccessDto>>> result =
                controller.grant(2L, req, admin);

        assertEquals(200, result.getStatusCode().value());
        // 仅 11L 触发 save（10L 已存在跳过）
        verify(accessRepository, times(1)).save(any(UserCategoryAccess.class));
    }

    @Test
    @DisplayName("3. 非本人非 ADMIN 查询授权被拒绝")
    void nonAdminNonSelfQueryDenied() {
        SecurityException ex = assertThrows(SecurityException.class, () ->
                controller.list(2L, otherUser));
        assertTrue(ex.getMessage().contains("无权查询"));
    }

    @Test
    @DisplayName("4. ADMIN 撤销某个分类授权")
    void adminRevokeCategorySuccess() {
        when(userRepository.findById(2L)).thenReturn(Optional.of(targetUser));

        ResponseEntity<ApiResponse<Void>> result =
                controller.revoke(2L, 10L, admin);

        assertNotNull(result);
        assertEquals(200, result.getStatusCode().value());
        verify(accessRepository).deleteByUserIdAndCategoryId(2L, 10L);
    }

    @Test
    @DisplayName("5. SYSTEM 分类整批拒绝（不写入）")
    void systemCategoryRejectedEntireBatch() {
        when(userRepository.findById(2L)).thenReturn(Optional.of(targetUser));
        // 批量中包含 1 个 SYSTEM 分类
        when(categoryRepository.findAllById(any(java.util.Set.class)))
                .thenReturn(List.of(researchCat1, systemCat));

        CategoryAccessRequest req = new CategoryAccessRequest();
        req.setCategoryIds(List.of(10L, 1L));

        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class, () ->
                controller.grant(2L, req, admin));
        assertTrue(ex.getMessage().contains("仅可授权 RESEARCH 资料分类"));
        // 整批拒绝：不应有任何 save
        verify(accessRepository, never()).save(any());
    }

    @Test
    @DisplayName("6. 空分类列表抛异常")
    void emptyCategoryListThrowsException() {
        when(userRepository.findById(2L)).thenReturn(Optional.of(targetUser));

        CategoryAccessRequest req = new CategoryAccessRequest();
        req.setCategoryIds(List.of());

        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class, () ->
                controller.grant(2L, req, admin));
        assertTrue(ex.getMessage().contains("不能为空"));
    }

    private User createUser(Long id, String username, Role role) {
        User u = new User();
        u.setId(id);
        u.setUsername(username);
        u.setRole(role);
        return u;
    }
}
