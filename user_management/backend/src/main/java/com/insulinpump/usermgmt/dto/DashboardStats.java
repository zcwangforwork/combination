package com.insulinpump.usermgmt.dto;

public class DashboardStats {

    private long totalEmployees;
    private long activeEmployees;
    private long totalDepartments;
    private long totalRoles;
    private java.util.Map<String, Long> employeesByRole;
    private java.util.Map<String, Long> employeesByDepartment;

    public long getTotalEmployees() { return totalEmployees; }
    public void setTotalEmployees(long totalEmployees) { this.totalEmployees = totalEmployees; }

    public long getActiveEmployees() { return activeEmployees; }
    public void setActiveEmployees(long activeEmployees) { this.activeEmployees = activeEmployees; }

    public long getTotalDepartments() { return totalDepartments; }
    public void setTotalDepartments(long totalDepartments) { this.totalDepartments = totalDepartments; }

    public long getTotalRoles() { return totalRoles; }
    public void setTotalRoles(long totalRoles) { this.totalRoles = totalRoles; }

    public java.util.Map<String, Long> getEmployeesByRole() { return employeesByRole; }
    public void setEmployeesByRole(java.util.Map<String, Long> employeesByRole) { this.employeesByRole = employeesByRole; }

    public java.util.Map<String, Long> getEmployeesByDepartment() { return employeesByDepartment; }
    public void setEmployeesByDepartment(java.util.Map<String, Long> employeesByDepartment) { this.employeesByDepartment = employeesByDepartment; }
}
