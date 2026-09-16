package com.insulinpump.usermgmt.repository;

import com.insulinpump.usermgmt.model.ResearchData;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.JpaSpecificationExecutor;

/**
 * 研发数据 Repository
 *
 * 使用 JpaSpecificationExecutor 支持多条件动态查询
 * （类型/分类/关键词/保密等级/owner 等过滤逻辑见 ResearchDataService.buildSpecification()）
 */
public interface ResearchDataRepository extends JpaRepository<ResearchData, Long>,
        JpaSpecificationExecutor<ResearchData> {
}
