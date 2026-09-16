package com.insulinpump.usermgmt.repository;

import com.insulinpump.usermgmt.model.AuditLog;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

/**
 * 审计日志 Repository
 *
 * 注意：不暴露 delete/deleteAll 方法（JpaRepository 自带但不调用）。
 * 审计日志只允许 INSERT + SELECT，不允许 UPDATE + DELETE。
 * @Immutable 注解在实体层阻止 UPDATE。
 */
public interface AuditLogRepository extends JpaRepository<AuditLog, Long> {

    Page<AuditLog> findByUserIdOrderByTimestampDesc(Long userId, Pageable pageable);

    Page<AuditLog> findByEntityTypeAndEntityIdOrderByTimestampDesc(
            String entityType, Long entityId, Pageable pageable);

    Page<AuditLog> findByActionOrderByTimestampDesc(String action, Pageable pageable);

    Page<AuditLog> findByResultOrderByTimestampDesc(String result, Pageable pageable);

    Page<AuditLog> findAllByOrderByTimestampDesc(Pageable pageable);
}
