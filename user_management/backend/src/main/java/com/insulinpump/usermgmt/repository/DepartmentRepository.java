package com.insulinpump.usermgmt.repository;

import com.insulinpump.usermgmt.model.Department;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

import java.util.Optional;

@Repository
public interface DepartmentRepository extends JpaRepository<Department, Long> {

    Optional<Department> findByName(String name);

    boolean existsByName(String name);

    /**
     * 查询部门负责人的 user_id（仅返回 Long，避免触发 User 实体的 EAGER 加载循环）
     *
     * 用于 JwtAuthFilter 计算 user.departmentLeader 字段，每次请求调用一次。
     * 单值查询性能优于 fetch join，且不会触发 leader User 的 Role/Department 级联加载。
     */
    @Query("SELECT d.leader.id FROM Department d WHERE d.id = :deptId")
    Optional<Long> findLeaderIdById(@Param("deptId") Long deptId);
}
