package com.insulinpump.usermgmt.dto;

import java.util.Set;

public class LoginResponse {

    private String token;
    private String tokenType = "Bearer";
    private Long userId;
    private String username;
    private String realName;
    private String employeeNo;
    private String roleName;
    private String roleCode;
    private Set<String> permissions;

    public LoginResponse(String token, Long userId, String username, String realName,
                         String employeeNo, String roleName, String roleCode, Set<String> permissions) {
        this.token = token;
        this.userId = userId;
        this.username = username;
        this.realName = realName;
        this.employeeNo = employeeNo;
        this.roleName = roleName;
        this.roleCode = roleCode;
        this.permissions = permissions;
    }

    public String getToken() { return token; }
    public void setToken(String token) { this.token = token; }

    public String getTokenType() { return tokenType; }
    public void setTokenType(String tokenType) { this.tokenType = tokenType; }

    public Long getUserId() { return userId; }
    public void setUserId(Long userId) { this.userId = userId; }

    public String getUsername() { return username; }
    public void setUsername(String username) { this.username = username; }

    public String getRealName() { return realName; }
    public void setRealName(String realName) { this.realName = realName; }

    public String getEmployeeNo() { return employeeNo; }
    public void setEmployeeNo(String employeeNo) { this.employeeNo = employeeNo; }

    public String getRoleName() { return roleName; }
    public void setRoleName(String roleName) { this.roleName = roleName; }

    public String getRoleCode() { return roleCode; }
    public void setRoleCode(String roleCode) { this.roleCode = roleCode; }

    public Set<String> getPermissions() { return permissions; }
    public void setPermissions(Set<String> permissions) { this.permissions = permissions; }
}
