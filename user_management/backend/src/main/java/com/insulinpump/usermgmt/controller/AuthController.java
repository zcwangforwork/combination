package com.insulinpump.usermgmt.controller;

import com.insulinpump.usermgmt.dto.*;
import com.insulinpump.usermgmt.model.User;
import com.insulinpump.usermgmt.service.AuthService;
import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/auth")
public class AuthController {

    private final AuthService authService;

    public AuthController(AuthService authService) {
        this.authService = authService;
    }

    @PostMapping("/login")
    public ResponseEntity<ApiResponse<LoginResponse>> login(@Valid @RequestBody LoginRequest request) {
        LoginResponse response = authService.login(request);
        return ResponseEntity.ok(ApiResponse.success("登录成功", response));
    }

    @PostMapping("/register")
    public ResponseEntity<ApiResponse<LoginResponse>> register(@Valid @RequestBody EmployeeDto dto) {
        LoginResponse response = authService.register(dto);
        return ResponseEntity.ok(ApiResponse.success("注册成功", response));
    }

    @GetMapping("/me")
    public ResponseEntity<ApiResponse<LoginResponse>> me(@AuthenticationPrincipal User user) {
        LoginResponse response = authService.getCurrentUser(user.getId());
        return ResponseEntity.ok(ApiResponse.success(response));
    }
}
