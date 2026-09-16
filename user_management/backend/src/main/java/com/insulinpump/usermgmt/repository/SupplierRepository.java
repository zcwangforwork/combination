package com.insulinpump.usermgmt.repository;

import com.insulinpump.usermgmt.model.Supplier;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.JpaSpecificationExecutor;

import java.util.Optional;

/**
 * 供应商 Repository
 *
 * 使用 JpaSpecificationExecutor 支持多条件动态查询
 * （分类/合格状态/关键词/enabled 过滤逻辑见 SupplierService.buildSpecification()）
 */
public interface SupplierRepository extends JpaRepository<Supplier, Long>,
        JpaSpecificationExecutor<Supplier> {

    /** 按供应商编码查找（用于唯一性校验） */
    Optional<Supplier> findBySupplierCode(String supplierCode);

    /** 用于唯一性校验：排除自身 ID 后判断编码是否已被其他供应商使用 */
    boolean existsBySupplierCodeAndIdNot(String supplierCode, Long id);
}
