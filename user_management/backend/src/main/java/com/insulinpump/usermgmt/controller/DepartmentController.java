package com.insulinpump.usermgmt.controller;

import com.insulinpump.usermgmt.dto.ApiResponse;
import com.insulinpump.usermgmt.model.Department;
import com.insulinpump.usermgmt.model.User;
import com.insulinpump.usermgmt.repository.DepartmentRepository;
import com.insulinpump.usermgmt.repository.UserRepository;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;

import java.util.List;

@RestController
@RequestMapping("/api/departments")
public class DepartmentController {

    private final DepartmentRepository departmentRepository;
    private final UserRepository userRepository;

    public DepartmentController(DepartmentRepository departmentRepository,
                                UserRepository userRepository) {
        this.departmentRepository = departmentRepository;
        this.userRepository = userRepository;
    }

    @GetMapping
    public ResponseEntity<ApiResponse<List<Department>>> listDepartments() {
        return ResponseEntity.ok(ApiResponse.success(departmentRepository.findAll()));
    }

    /**
     * 设置部门负责人
     *
     * 部门负责人可查看本部门所有数据（含全部保密等级）。
     * 调岗/卸任时将 leaderId 置空可取消负责人标识。
     *
     * 权限：仅 ADMIN
     *
     * 注意：调岗时请同步更新原部门的 leader，避免遗留权限。
     */
    @PutMapping("/{id}/leader")
    @PreAuthorize("hasRole('ADMIN')")
    public ResponseEntity<ApiResponse<Department>> setLeader(
            @PathVariable Long id,
            @RequestParam(required = false) Long leaderId) {
        Department dept = departmentRepository.findById(id)
                .orElseThrow(() -> new IllegalArgumentException("部门不存在"));

        if (leaderId == null) {
            // 卸任：清除负责人
            dept.setLeader(null);
        } else {
            User leader = userRepository.findById(leaderId)
                    .orElseThrow(() -> new IllegalArgumentException("用户不存在"));
            // 校验：被设置人应属于该部门（避免跨部门设置）
            if (leader.getDepartment() == null
                    || !leader.getDepartment().getId().equals(dept.getId())) {
                throw new IllegalArgumentException("被设置人不在该部门内");
            }
            dept.setLeader(leader);
        }

        Department saved = departmentRepository.save(dept);
        return ResponseEntity.ok(ApiResponse.success("设置成功", saved));
    }
}
