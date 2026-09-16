package com.insulinpump.usermgmt.service;

import com.insulinpump.usermgmt.dto.DashboardStats;
import com.insulinpump.usermgmt.repository.DepartmentRepository;
import com.insulinpump.usermgmt.repository.RoleRepository;
import com.insulinpump.usermgmt.repository.UserRepository;
import org.springframework.stereotype.Service;

import java.util.HashMap;
import java.util.Map;

@Service
public class DashboardService {

    private final UserRepository userRepository;
    private final RoleRepository roleRepository;
    private final DepartmentRepository departmentRepository;

    public DashboardService(UserRepository userRepository, RoleRepository roleRepository,
                            DepartmentRepository departmentRepository) {
        this.userRepository = userRepository;
        this.roleRepository = roleRepository;
        this.departmentRepository = departmentRepository;
    }

    public DashboardStats getStats() {
        DashboardStats stats = new DashboardStats();
        stats.setTotalEmployees(userRepository.count());
        stats.setActiveEmployees(userRepository.countByEnabled(true));
        stats.setTotalDepartments(departmentRepository.count());
        stats.setTotalRoles(roleRepository.count());

        Map<String, Long> byRole = new HashMap<>();
        roleRepository.findAll().forEach(role -> {
            long count = userRepository.findAll().stream()
                    .filter(u -> u.getRole() != null && u.getRole().getId().equals(role.getId()))
                    .count();
            byRole.put(role.getName(), count);
        });
        stats.setEmployeesByRole(byRole);

        Map<String, Long> byDept = new HashMap<>();
        departmentRepository.findAll().forEach(dept -> {
            long count = userRepository.findAll().stream()
                    .filter(u -> u.getDepartment() != null
                            && u.getDepartment().getId().equals(dept.getId()))
                    .count();
            byDept.put(dept.getName(), count);
        });
        stats.setEmployeesByDepartment(byDept);

        return stats;
    }
}
