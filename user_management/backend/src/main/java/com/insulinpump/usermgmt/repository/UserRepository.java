package com.insulinpump.usermgmt.repository;

import com.insulinpump.usermgmt.model.User;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.JpaSpecificationExecutor;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.Optional;

@Repository
public interface UserRepository extends JpaRepository<User, Long>, JpaSpecificationExecutor<User> {

    Optional<User> findByUsername(String username);

    boolean existsByUsername(String username);

    boolean existsByEmployeeNo(String employeeNo);

    long countByEnabled(Boolean enabled);

    /** 所有启用状态的用户（系统公告广播） */
    List<User> findByEnabledTrue();

    /** 所有启用状态、指定角色的用户（如 ADMIN，用于审批待办广播） */
    List<User> findByEnabledTrueAndRole_Code(String roleCode);
}
