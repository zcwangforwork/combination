package com.insulinpump.usermgmt.service;

import com.insulinpump.usermgmt.dto.EmployeeDto;
import com.insulinpump.usermgmt.dto.EmployeeListDto;
import com.insulinpump.usermgmt.model.Department;
import com.insulinpump.usermgmt.model.Role;
import com.insulinpump.usermgmt.model.User;
import com.insulinpump.usermgmt.repository.DepartmentRepository;
import com.insulinpump.usermgmt.repository.RoleRepository;
import com.insulinpump.usermgmt.repository.UserRepository;
import jakarta.persistence.criteria.Predicate;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.data.jpa.domain.Specification;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;

import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.List;

@Service
public class EmployeeService {

    private final UserRepository userRepository;
    private final RoleRepository roleRepository;
    private final DepartmentRepository departmentRepository;
    private final PasswordEncoder passwordEncoder;

    private static final DateTimeFormatter DTF = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");

    public EmployeeService(UserRepository userRepository, RoleRepository roleRepository,
                           DepartmentRepository departmentRepository,
                           PasswordEncoder passwordEncoder) {
        this.userRepository = userRepository;
        this.roleRepository = roleRepository;
        this.departmentRepository = departmentRepository;
        this.passwordEncoder = passwordEncoder;
    }

    public Page<EmployeeListDto> listEmployees(int page, int size, String keyword,
                                               Long departmentId, String roleCode, Boolean enabled) {
        PageRequest pr = PageRequest.of(page, size, Sort.by(Sort.Direction.DESC, "createTime"));
        Specification<User> spec = (root, query, cb) -> {
            List<Predicate> predicates = new ArrayList<>();
            if (keyword != null && !keyword.isBlank()) {
                String like = "%" + keyword.trim().toLowerCase() + "%";
                predicates.add(cb.or(
                        cb.like(cb.lower(root.get("realName")), like),
                        cb.like(cb.lower(root.get("username")), like),
                        cb.like(cb.lower(root.get("employeeNo")), like),
                        cb.like(cb.lower(root.get("phone")), like)
                ));
            }
            if (departmentId != null) {
                predicates.add(cb.equal(root.get("department").get("id"), departmentId));
            }
            if (roleCode != null && !roleCode.isBlank()) {
                predicates.add(cb.equal(root.get("role").get("code"), roleCode));
            }
            if (enabled != null) {
                predicates.add(cb.equal(root.get("enabled"), enabled));
            }
            return cb.and(predicates.toArray(new Predicate[0]));
        };
        Page<User> users = userRepository.findAll(spec, pr);
        return users.map(this::toListDto);
    }

    public User getEmployee(Long id) {
        return userRepository.findById(id)
                .orElseThrow(() -> new IllegalArgumentException("员工不存在"));
    }

    public User createEmployee(EmployeeDto dto) {
        if (userRepository.existsByUsername(dto.getUsername())) {
            throw new IllegalArgumentException("用户名已存在");
        }

        Role role = roleRepository.findByCode(dto.getRoleCode())
                .orElseThrow(() -> new IllegalArgumentException("角色不存在"));

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

        return userRepository.save(user);
    }

    public User updateEmployee(Long id, EmployeeDto dto) {
        User user = userRepository.findById(id)
                .orElseThrow(() -> new IllegalArgumentException("员工不存在"));

        if (dto.getRealName() != null) user.setRealName(dto.getRealName());
        if (dto.getPassword() != null && !dto.getPassword().isBlank()) {
            user.setPassword(passwordEncoder.encode(dto.getPassword()));
        }
        if (dto.getEmployeeNo() != null) user.setEmployeeNo(dto.getEmployeeNo());
        if (dto.getEmail() != null) user.setEmail(dto.getEmail());
        if (dto.getPhone() != null) user.setPhone(dto.getPhone());
        if (dto.getEnabled() != null) user.setEnabled(dto.getEnabled());

        if (dto.getRoleCode() != null) {
            Role role = roleRepository.findByCode(dto.getRoleCode())
                    .orElseThrow(() -> new IllegalArgumentException("角色不存在"));
            user.setRole(role);
        }

        if (dto.getDepartmentName() != null) {
            Department department = departmentRepository.findByName(dto.getDepartmentName())
                    .orElseGet(() -> {
                        Department dept = new Department(dto.getDepartmentName(), "", null);
                        return departmentRepository.save(dept);
                    });
            user.setDepartment(department);
        }

        return userRepository.save(user);
    }

    public void deleteEmployee(Long id) {
        User user = userRepository.findById(id)
                .orElseThrow(() -> new IllegalArgumentException("员工不存在"));
        userRepository.delete(user);
    }

    private EmployeeListDto toListDto(User user) {
        return new EmployeeListDto(
                user.getId(),
                user.getUsername(),
                user.getRealName(),
                user.getEmployeeNo(),
                user.getEmail(),
                user.getPhone(),
                user.getRole() != null ? user.getRole().getName() : null,
                user.getRole() != null ? user.getRole().getCode() : null,
                user.getDepartment() != null ? user.getDepartment().getName() : null,
                user.getEnabled(),
                user.getCreateTime() != null ? user.getCreateTime().format(DTF) : null
        );
    }
}
