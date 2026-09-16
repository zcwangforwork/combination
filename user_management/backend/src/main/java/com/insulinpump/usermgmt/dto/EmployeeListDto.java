package com.insulinpump.usermgmt.dto;

public class EmployeeListDto {

    private Long id;
    private String username;
    private String realName;
    private String employeeNo;
    private String email;
    private String phone;
    private String roleName;
    private String roleCode;
    private String departmentName;
    private Boolean enabled;
    private String createTime;

    public EmployeeListDto(Long id, String username, String realName, String employeeNo,
                           String email, String phone, String roleName, String roleCode,
                           String departmentName, Boolean enabled, String createTime) {
        this.id = id;
        this.username = username;
        this.realName = realName;
        this.employeeNo = employeeNo;
        this.email = email;
        this.phone = phone;
        this.roleName = roleName;
        this.roleCode = roleCode;
        this.departmentName = departmentName;
        this.enabled = enabled;
        this.createTime = createTime;
    }

    public Long getId() { return id; }
    public String getUsername() { return username; }
    public String getRealName() { return realName; }
    public String getEmployeeNo() { return employeeNo; }
    public String getEmail() { return email; }
    public String getPhone() { return phone; }
    public String getRoleName() { return roleName; }
    public String getRoleCode() { return roleCode; }
    public String getDepartmentName() { return departmentName; }
    public Boolean getEnabled() { return enabled; }
    public String getCreateTime() { return createTime; }
}
