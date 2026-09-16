package com.insulinpump.usermgmt.config;

import com.insulinpump.usermgmt.model.User;
import com.insulinpump.usermgmt.repository.DepartmentRepository;
import com.insulinpump.usermgmt.repository.UserRepository;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

@Component
public class JwtAuthFilter extends OncePerRequestFilter {

    private final JwtUtil jwtUtil;
    private final UserRepository userRepository;
    private final DepartmentRepository departmentRepository;

    public JwtAuthFilter(JwtUtil jwtUtil, UserRepository userRepository,
                         DepartmentRepository departmentRepository) {
        this.jwtUtil = jwtUtil;
        this.userRepository = userRepository;
        this.departmentRepository = departmentRepository;
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request,
                                    HttpServletResponse response,
                                    FilterChain filterChain) throws ServletException, IOException {
        String token = extractToken(request);

        if (token != null && jwtUtil.validateToken(token)) {
            String username = jwtUtil.getUsernameFromToken(token);
            Optional<User> userOpt = userRepository.findByUsername(username);

            if (userOpt.isPresent() && userOpt.get().getEnabled()) {
                User user = userOpt.get();

                // 计算部门负责人标识（@Transient 字段，DataVisibilityChecker.isDeptLeader 使用）
                // 单独查询 leader_id 避免触发 Department.leader 的 User 实体 EAGER 级联加载
                if (user.getDepartment() != null) {
                    Long deptId = user.getDepartment().getId();
                    Optional<Long> leaderIdOpt = departmentRepository.findLeaderIdById(deptId);
                    if (leaderIdOpt.isPresent() && leaderIdOpt.get().equals(user.getId())) {
                        user.setDepartmentLeader(true);
                    }
                }

                List<SimpleGrantedAuthority> authorities = new ArrayList<>();
                // 角色：支持 hasRole('ADMIN') / hasAnyRole(...)（Spring 自动加 ROLE_ 前缀）
                authorities.add(new SimpleGrantedAuthority("ROLE_" + user.getRole().getCode()));
                // 细粒度权限：支持 hasAuthority('supplier:read') 等
                if (user.getRole().getPermissions() != null) {
                    for (String perm : user.getRole().getPermissions()) {
                        authorities.add(new SimpleGrantedAuthority(perm));
                    }
                }

                UsernamePasswordAuthenticationToken authentication =
                        new UsernamePasswordAuthenticationToken(user, null, authorities);
                SecurityContextHolder.getContext().setAuthentication(authentication);
            }
        }

        filterChain.doFilter(request, response);
    }

    private String extractToken(HttpServletRequest request) {
        String bearerToken = request.getHeader("Authorization");
        if (StringUtils.hasText(bearerToken) && bearerToken.startsWith("Bearer ")) {
            return bearerToken.substring(7);
        }
        return null;
    }
}
