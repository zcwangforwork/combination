package com.insulinpump.usermgmt.dto;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

public class EmployeeDto {

    @NotBlank(message = "用户名不能为空")
    private String username;

    @NotBlank(message = "姓名不能为空")
    private String realName;

    private String password;

    private String employeeNo;

    @Email(message = "邮箱格式不正确")
    private String email;

    private String phone;

    @NotBlank(message = "角色编码不能为空")
    private String roleCode;

    private String departmentName;

    private Boolean enabled;

    /** [SEC 2026-09-28] 保密密级 0-3（0公开/1内部/2秘密/3机密）；缺省 0=公开 */
    @Min(value = 0, message = "密级不能小于 0")
    @Max(value = 3, message = "密级不能大于 3")
    private Integer secLevel;

    public String getUsername() { return username; }
    public void setUsername(String username) { this.username = username; }

    public String getRealName() { return realName; }
    public void setRealName(String realName) { this.realName = realName; }

    public String getPassword() { return password; }
    public void setPassword(String password) { this.password = password; }

    public String getEmployeeNo() { return employeeNo; }
    public void setEmployeeNo(String employeeNo) { this.employeeNo = employeeNo; }

    public String getEmail() { return email; }
    public void setEmail(String email) { this.email = email; }

    public String getPhone() { return phone; }
    public void setPhone(String phone) { this.phone = phone; }

    public String getRoleCode() { return roleCode; }
    public void setRoleCode(String roleCode) { this.roleCode = roleCode; }

    public String getDepartmentName() { return departmentName; }
    public void setDepartmentName(String departmentName) { this.departmentName = departmentName; }

    public Boolean getEnabled() { return enabled; }
    public void setEnabled(Boolean enabled) { this.enabled = enabled; }

    public Integer getSecLevel() { return secLevel; }
    public void setSecLevel(Integer secLevel) { this.secLevel = secLevel; }
}
