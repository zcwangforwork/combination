package com.insulinpump.usermgmt.repository;

import com.insulinpump.usermgmt.model.CommercialRecord;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.JpaSpecificationExecutor;

/**
 * 商业成本记录 Repository
 *
 * 使用 JpaSpecificationExecutor 支持多条件动态查询
 * （供应商/保密等级/owner/生效日期范围 见 CommercialRecordService.buildSpecification()）
 */
public interface CommercialRecordRepository extends JpaRepository<CommercialRecord, Long>,
        JpaSpecificationExecutor<CommercialRecord> {
}
