package com.insulinpump.usermgmt.controller;

import com.insulinpump.usermgmt.dto.ApiResponse;
import com.insulinpump.usermgmt.dto.ConfidentialityAccessDto;
import com.insulinpump.usermgmt.dto.ConfidentialityAccessRequest;
import com.insulinpump.usermgmt.model.ConfidentialityLevel;
import com.insulinpump.usermgmt.model.Role;
import com.insulinpump.usermgmt.model.User;
import com.insulinpump.usermgmt.model.UserConfidentialityAccess;
import com.insulinpump.usermgmt.repository.UserConfidentialityAccessRepository;
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
 * ConfidentialityAccessController 单元测试
 *
 * 覆盖 4 个核心场景：
 *   1. ADMIN 授予用户保密等级（幂等：已存在直接返回）
 *   2. 非本人非 ADMIN 查询授权被拒绝
 *   3. ADMIN 撤销用户保密等级
 *   4. 无效保密等级抛异常
 */
@ExtendWith(MockitoExtension.class)
@MockitoSettings(strictness = Strictness.LENIENT)
class ConfidentialityAccessControllerTest {

    @Mock
    private UserConfidentialityAccessRepository accessRepository;

    @Mock
    private UserRepository userRepository;

    @InjectMocks
    private ConfidentialityAccessController controller;

    private User admin;
    private User targetUser;
    private User otherUser;

    @BeforeEach
    void setUp() {
        Role adminRole = new Role("管理员", "ADMIN", "");
        Role engrRole = new Role("结构工程师", "STRUCTURAL_ENGINEER", "");

        admin = createUser(1L, "admin", adminRole);
        targetUser = createUser(2L, "zhangsan", engrRole);
        otherUser = createUser(3L, "lisi", engrRole);
    }

    @Test
    @DisplayName("1. ADMIN 授予用户保密等级（首次创建）")
    void adminGrantNewLevelSuccess() {
        when(userRepository.findById(2L)).thenReturn(Optional.of(targetUser));
        when(accessRepository.existsByUserIdAndConfidentialityLevel(2L, ConfidentialityLevel.CONFIDENTIAL))
                .thenReturn(false);
        when(accessRepository.save(any(UserConfidentialityAccess.class)))
                .thenAnswer(inv -> inv.getArgument(0));

        ConfidentialityAccessRequest req = new ConfidentialityAccessRequest();
        req.setConfidentialityLevel("CONFIDENTIAL");

        ResponseEntity<ApiResponse<ConfidentialityAccessDto>> result =
                controller.grant(2L, req, admin);

        assertNotNull(result);
        assertEquals(200, result.getStatusCode().value());
        assertEquals("CONFIDENTIAL", result.getBody().getData().getConfidentialityLevel());
        verify(accessRepository).save(any(UserConfidentialityAccess.class));
    }

    @Test
    @DisplayName("1b. ADMIN 授予已存在等级（幂等返回）")
    void adminGrantExistingLevelIdempotent() {
        UserConfidentialityAccess existing = new UserConfidentialityAccess(
                targetUser, ConfidentialityLevel.CONFIDENTIAL, admin);
        existing.setId(10L);

        when(userRepository.findById(2L)).thenReturn(Optional.of(targetUser));
        when(accessRepository.existsByUserIdAndConfidentialityLevel(2L, ConfidentialityLevel.CONFIDENTIAL))
                .thenReturn(true);
        when(accessRepository.findByUserId(2L)).thenReturn(List.of(existing));

        ConfidentialityAccessRequest req = new ConfidentialityAccessRequest();
        req.setConfidentialityLevel("CONFIDENTIAL");

        ResponseEntity<ApiResponse<ConfidentialityAccessDto>> result =
                controller.grant(2L, req, admin);

        assertEquals("已授权（幂等）", result.getBody().getMessage());
        verify(accessRepository, never()).save(any());
    }

    @Test
    @DisplayName("2. 非本人非 ADMIN 查询授权被拒绝")
    void nonAdminNonSelfQueryDenied() {
        // otherUser 查询 targetUser 的授权
        SecurityException ex = assertThrows(SecurityException.class, () ->
                controller.list(2L, otherUser));
        assertTrue(ex.getMessage().contains("无权查询"));
    }

    @Test
    @DisplayName("3. ADMIN 撤销用户保密等级")
    void adminRevokeLevelSuccess() {
        when(userRepository.findById(2L)).thenReturn(Optional.of(targetUser));

        ResponseEntity<ApiResponse<Void>> result =
                controller.revoke(2L, "CONFIDENTIAL", admin);

        assertNotNull(result);
        assertEquals(200, result.getStatusCode().value());
        verify(accessRepository).deleteByUserIdAndConfidentialityLevel(2L, ConfidentialityLevel.CONFIDENTIAL);
    }

    @Test
    @DisplayName("4. 无效保密等级抛异常")
    void invalidLevelThrowsException() {
        when(userRepository.findById(2L)).thenReturn(Optional.of(targetUser));

        ConfidentialityAccessRequest req = new ConfidentialityAccessRequest();
        req.setConfidentialityLevel("INVALID_LEVEL");

        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class, () ->
                controller.grant(2L, req, admin));
        assertTrue(ex.getMessage().contains("无效的保密等级"));
    }

    private User createUser(Long id, String username, Role role) {
        User u = new User();
        u.setId(id);
        u.setUsername(username);
        u.setRole(role);
        return u;
    }
}
