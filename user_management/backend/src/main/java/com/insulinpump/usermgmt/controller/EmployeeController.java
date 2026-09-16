package com.insulinpump.usermgmt.controller;

import com.insulinpump.usermgmt.dto.*;
import com.insulinpump.usermgmt.model.User;
import com.insulinpump.usermgmt.service.EmployeeService;
import jakarta.validation.Valid;
import org.springframework.data.domain.Page;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/employees")
public class EmployeeController {

    private final EmployeeService employeeService;

    public EmployeeController(EmployeeService employeeService) {
        this.employeeService = employeeService;
    }

    @GetMapping
    public ResponseEntity<ApiResponse<Page<EmployeeListDto>>> list(
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size,
            @RequestParam(required = false) String keyword,
            @RequestParam(required = false) Long departmentId,
            @RequestParam(required = false) String roleCode,
            @RequestParam(required = false) Boolean enabled) {
        Page<EmployeeListDto> result = employeeService.listEmployees(page, size, keyword, departmentId, roleCode, enabled);
        return ResponseEntity.ok(ApiResponse.success(result));
    }

    @GetMapping("/{id}")
    public ResponseEntity<ApiResponse<User>> getById(@PathVariable Long id) {
        User user = employeeService.getEmployee(id);
        user.setPassword(null);
        return ResponseEntity.ok(ApiResponse.success(user));
    }

    @PostMapping
    @PreAuthorize("hasRole('ADMIN')")
    public ResponseEntity<ApiResponse<User>> create(@Valid @RequestBody EmployeeDto dto) {
        User user = employeeService.createEmployee(dto);
        user.setPassword(null);
        return ResponseEntity.ok(ApiResponse.success("创建成功", user));
    }

    @PutMapping("/{id}")
    @PreAuthorize("hasRole('ADMIN')")
    public ResponseEntity<ApiResponse<User>> update(@PathVariable Long id,
                                                     @RequestBody EmployeeDto dto) {
        User user = employeeService.updateEmployee(id, dto);
        user.setPassword(null);
        return ResponseEntity.ok(ApiResponse.success("更新成功", user));
    }

    @DeleteMapping("/{id}")
    @PreAuthorize("hasRole('ADMIN')")
    public ResponseEntity<ApiResponse<Void>> delete(@PathVariable Long id) {
        employeeService.deleteEmployee(id);
        return ResponseEntity.ok(ApiResponse.success("删除成功", null));
    }
}
