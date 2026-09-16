package com.insulinpump.usermgmt.service;

import com.insulinpump.usermgmt.config.JwtUtil;
import com.insulinpump.usermgmt.dto.EmployeeDto;
import com.insulinpump.usermgmt.dto.LoginRequest;
import com.insulinpump.usermgmt.dto.LoginResponse;
import com.insulinpump.usermgmt.model.Department;
import com.insulinpump.usermgmt.model.Role;
import com.insulinpump.usermgmt.model.User;
import com.insulinpump.usermgmt.repository.DepartmentRepository;
import com.insulinpump.usermgmt.repository.RoleRepository;
import com.insulinpump.usermgmt.repository.UserRepository;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;

@Service
public class AuthService {

    private final UserRepository userRepository;
    private final RoleRepository roleRepository;
    private final DepartmentRepository departmentRepository;
    private final PasswordEncoder passwordEncoder;
    private final JwtUtil jwtUtil;

    public AuthService(UserRepository userRepository, RoleRepository roleRepository,
                       DepartmentRepository departmentRepository,
                       PasswordEncoder passwordEncoder, JwtUtil jwtUtil) {
        this.userRepository = userRepository;
        this.roleRepository = roleRepository;
        this.departmentRepository = departmentRepository;
        this.passwordEncoder = passwordEncoder;
        this.jwtUtil = jwtUtil;
    }

    public LoginResponse login(LoginRequest request) {
        User user = userRepository.findByUsername(request.getUsername())
                .orElseThrow(() -> new BadCredentialsException("用户名或密码错误"));

        if (!user.getEnabled()) {
            throw new BadCredentialsException("账户已被禁用");
        }

        if (!passwordEncoder.matches(request.getPassword(), user.getPassword())) {
            throw new BadCredentialsException("用户名或密码错误");
        }

        String token = jwtUtil.generateToken(user.getUsername(), user.getId(),
                user.getRole().getCode());

        return new LoginResponse(
                token, user.getId(), user.getUsername(), user.getRealName(),
                user.getEmployeeNo(), user.getRole().getName(), user.getRole().getCode(),
                user.getRole().getPermissions()
        );
    }

    public LoginResponse register(EmployeeDto dto) {
        if (userRepository.existsByUsername(dto.getUsername())) {
            throw new IllegalArgumentException("用户名已存在");
        }
        if (dto.getEmployeeNo() != null && userRepository.existsByEmployeeNo(dto.getEmployeeNo())) {
            throw new IllegalArgumentException("工号已存在");
        }

        Role role = roleRepository.findByCode(dto.getRoleCode())
                .orElseThrow(() -> new IllegalArgumentException("角色不存在: " + dto.getRoleCode()));

        Department department = null;
        if (dto.getDepartmentName() != null && !dto.getDepartmentName().isBlank()) {
            department = departmentRepository.findByName(dto.getDepartmentName())
                    .orElseGet(() -> {
                        Department dept = new Department(dto.getDepartmentName(), "", null);
                        return departmentRepository.save(dept);
                    });
        }

        User user = new User();
        user.setUsername(dto.getUsername());
        user.setPassword(passwordEncoder.encode(
                dto.getPassword() != null ? dto.getPassword() : "123456"));
        user.setRealName(dto.getRealName());
        user.setEmployeeNo(dto.getEmployeeNo());
        user.setEmail(dto.getEmail());
        user.setPhone(dto.getPhone());
        user.setRole(role);
        user.setDepartment(department);
        user.setEnabled(dto.getEnabled() != null ? dto.getEnabled() : true);

        user = userRepository.save(user);

        String token = jwtUtil.generateToken(user.getUsername(), user.getId(), role.getCode());
        return new LoginResponse(token, user.getId(), user.getUsername(), user.getRealName(),
                user.getEmployeeNo(), role.getName(), role.getCode(), role.getPermissions());
    }

    public LoginResponse getCurrentUser(Long userId) {
        User user = userRepository.findById(userId)
                .orElseThrow(() -> new IllegalArgumentException("用户不存在"));

        return new LoginResponse(null, user.getId(), user.getUsername(), user.getRealName(),
                user.getEmployeeNo(), user.getRole().getName(), user.getRole().getCode(),
                user.getRole().getPermissions());
    }
}
