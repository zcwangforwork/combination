package com.insulinpump.usermgmt.service;

import com.insulinpump.usermgmt.audit.Auditable;
import com.insulinpump.usermgmt.config.RequestContextFilter;
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
        // [SEC 2026-09-28] 密级缺省 0（公开，fail-closed）
        user.setSecLevel(dto.getSecLevel() != null ? dto.getSecLevel() : 0);

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
        // [SEC 2026-09-28] 密级可随员工信息更新；单独变更走 updateSecLevel（带审计 before 快照）
        if (dto.getSecLevel() != null) user.setSecLevel(dto.getSecLevel());

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

    /**
     * [SEC 2026-09-28] 用户保密密级变更（升密/降密），方案 §12 R2。
     *
     * 独立于通用 updateEmployee：变更前后值入审计日志（@Auditable +
     * setAuditBefore 快照）。变更落库后：
     *  - 新登录 token 立即携带新密级 claim；
     *  - Python 侧无 claim 旧 token 走 PG 回退查询，其 TTL 缓存
     *    （SEC_USER_CACHE_TTL，缺省 300s）内可能短暂取旧值，过期自动收敛。
     */
    @Auditable(action = "CHANGE_SEC_LEVEL", entityType = "USER")
    public User updateSecLevel(Long id, Integer newLevel, String reason) {
        if (newLevel == null || newLevel < 0 || newLevel > 3) {
            throw new IllegalArgumentException("密级必须在 0-3 之间");
        }
        User user = userRepository.findById(id)
                .orElseThrow(() -> new IllegalArgumentException("员工不存在"));
        Integer oldLevel = user.getSecLevel();
        if (newLevel.equals(oldLevel)) {
            return user; // 幂等：无变化不落库不审计
        }
        RequestContextFilter.setAuditBefore(
                "secLevel=" + oldLevel + " -> " + newLevel
                        + (reason != null && !reason.isBlank() ? ", reason=" + reason : ""));
        user.setSecLevel(newLevel);
        return userRepository.save(user);
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
                user.getCreateTime() != null ? user.getCreateTime().format(DTF) : null,
                user.getSecLevel()
        );
    }
}
