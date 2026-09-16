package com.insulinpump.usermgmt.service;

import com.insulinpump.usermgmt.dto.CommercialRecordDetailDto;
import com.insulinpump.usermgmt.dto.CommercialRecordListDto;
import com.insulinpump.usermgmt.dto.CommercialRecordRequest;
import com.insulinpump.usermgmt.model.*;
import com.insulinpump.usermgmt.repository.CommercialRecordRepository;
import com.insulinpump.usermgmt.repository.SupplierRepository;
import jakarta.persistence.criteria.Predicate;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.data.jpa.domain.Specification;
import org.springframework.orm.ObjectOptimisticLockingFailureException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.ArrayList;
import java.util.List;

/**
 * 商业成本记录 Service
 *
 * 可见性规则（统一通过 DataVisibilityChecker 实现）：
 *   - ADMIN       : 看全部记录
 *   - owner       : 看自己录入的所有等级记录
 *   - 同部门员工  : 看本部门他人录入的所有等级记录（所有员工，不限于部门负责人）
 *   - 跨部门授权  : allowedLevels 命中保密等级可见（由 ADMIN 显式授权）
 *   - 普通员工    : 看自己录入的 + 本部门他人 + allowedLevels 内的他人记录（默认空集 = 自己 + 本部门）
 *
 * 编辑/删除权限：owner 或 ADMIN
 *
 * 保密等级默认 CONFIDENTIAL（成本价是敏感商业数据）
 *
 * 关系图：每条记录必须关联一个非空 Supplier FK（来自 t_supplier 主数据）
 */
@Service
public class CommercialRecordService {

    private final CommercialRecordRepository commercialRecordRepository;
    private final SupplierRepository supplierRepository;
    private final DataVisibilityChecker dataVisibilityChecker;

    public CommercialRecordService(CommercialRecordRepository commercialRecordRepository,
                                    SupplierRepository supplierRepository,
                                    DataVisibilityChecker dataVisibilityChecker) {
        this.commercialRecordRepository = commercialRecordRepository;
        this.supplierRepository = supplierRepository;
        this.dataVisibilityChecker = dataVisibilityChecker;
    }

    // ============ 查询 ============

    /**
     * 分页查询商业成本记录
     *
     * @param view "mine"=我的 / "all"=全部(仅ADMIN) / "public"=全员可见 / 其他=mine∪public
     */
    @Transactional(readOnly = true)
    public Page<CommercialRecordListDto> list(int page, int size,
                                                Long supplierId, String keyword,
                                                String confidentialityLevel, String view,
                                                User currentUser) {
        Specification<CommercialRecord> spec = buildSpecification(
                supplierId, keyword, confidentialityLevel, view, currentUser);

        PageRequest pageable = PageRequest.of(page, size,
                Sort.by(Sort.Direction.DESC, "createdAt"));

        Page<CommercialRecord> pageResult = commercialRecordRepository.findAll(spec, pageable);
        return pageResult.map(d -> toListDto(d, currentUser));
    }

    @Transactional(readOnly = true)
    public CommercialRecordDetailDto getById(Long id, User currentUser) {
        CommercialRecord cr = commercialRecordRepository.findById(id)
                .orElseThrow(() -> new IllegalArgumentException("成本记录不存在"));
        checkVisibility(cr, currentUser);
        return toDetailDto(cr, currentUser);
    }

    // ============ 写操作 ============

    /**
     * 创建成本记录
     * 权限：任意已登录用户
     * 默认保密等级：CONFIDENTIAL
     */
    @Transactional
    public CommercialRecordDetailDto create(CommercialRecordRequest req, User currentUser) {
        validateRequest(req, true);

        CommercialRecord cr = new CommercialRecord();
        applyRequestToEntity(cr, req);

        // 保密等级默认 CONFIDENTIAL
        ConfidentialityLevel level = ConfidentialityLevel.CONFIDENTIAL;
        if (req.getConfidentialityLevel() != null && !req.getConfidentialityLevel().isBlank()) {
            level = ConfidentialityLevel.valueOf(req.getConfidentialityLevel().toUpperCase());
        }
        cr.setConfidentialityLevel(level);

        cr.setOwner(currentUser);

        CommercialRecord saved = commercialRecordRepository.save(cr);
        return toDetailDto(saved, currentUser);
    }

    /**
     * 更新成本记录（部分更新）
     * 权限：owner 或 ADMIN
     * 乐观锁：必须传 optimisticLockVersion
     */
    @Transactional
    public CommercialRecordDetailDto update(Long id, CommercialRecordRequest req, User currentUser) {
        CommercialRecord cr = commercialRecordRepository.findById(id)
                .orElseThrow(() -> new IllegalArgumentException("成本记录不存在"));
        if (!dataVisibilityChecker.canModify(currentUser, cr.getOwner(),
                cr.getConfidentialityLevel(), null, false)) {
            throw new SecurityException("无权修改该成本记录");
        }

        if (req.getOptimisticLockVersion() == null) {
            throw new IllegalArgumentException("缺少乐观锁版本号 optimisticLockVersion");
        }
        cr.setOptimisticLockVersion(req.getOptimisticLockVersion());

        validateRequest(req, false);
        applyRequestToEntity(cr, req);

        if (req.getConfidentialityLevel() != null && !req.getConfidentialityLevel().isBlank()) {
            cr.setConfidentialityLevel(
                    ConfidentialityLevel.valueOf(req.getConfidentialityLevel().toUpperCase()));
        }

        try {
            CommercialRecord saved = commercialRecordRepository.save(cr);
            return toDetailDto(saved, currentUser);
        } catch (ObjectOptimisticLockingFailureException e) {
            throw new IllegalArgumentException("该记录已被其他用户修改，请刷新后重试");
        }
    }

    /**
     * 删除成本记录
     * 权限：owner 或 ADMIN
     */
    @Transactional
    public void delete(Long id, User currentUser) {
        CommercialRecord cr = commercialRecordRepository.findById(id)
                .orElseThrow(() -> new IllegalArgumentException("成本记录不存在"));
        if (!dataVisibilityChecker.canModify(currentUser, cr.getOwner(),
                cr.getConfidentialityLevel(), null, false)) {
            throw new SecurityException("无权删除该成本记录");
        }
        commercialRecordRepository.delete(cr);
    }

    // ============ 私有辅助方法 ============

    private void validateRequest(CommercialRecordRequest req, boolean isCreate) {
        if (isCreate) {
            if (req.getSupplierId() == null) {
                throw new IllegalArgumentException("供应商不能为空");
            }
            if (req.getItemName() == null || req.getItemName().isBlank()) {
                throw new IllegalArgumentException("物料/项目名称不能为空");
            }
            if (req.getCostPrice() == null) {
                throw new IllegalArgumentException("成本价不能为空");
            }
            if (req.getCostPrice().signum() < 0) {
                throw new IllegalArgumentException("成本价不能为负数");
            }
            if (req.getEffectiveDate() == null) {
                throw new IllegalArgumentException("生效日期不能为空");
            }
        }
        if (req.getCurrency() != null && !req.getCurrency().isBlank()) {
            try {
                Currency.valueOf(req.getCurrency().toUpperCase());
            } catch (IllegalArgumentException e) {
                throw new IllegalArgumentException("无效的货币类型: " + req.getCurrency());
            }
        }
    }

    private void applyRequestToEntity(CommercialRecord cr, CommercialRecordRequest req) {
        if (req.getSupplierId() != null) {
            Supplier supplier = supplierRepository.findById(req.getSupplierId())
                    .orElseThrow(() -> new IllegalArgumentException("供应商不存在"));
            // 允许选择已停用的供应商（历史成本记录可能引用 disabled 供应商）
            cr.setSupplier(supplier);
        }
        if (req.getItemName() != null && !req.getItemName().isBlank()) {
            cr.setItemName(req.getItemName());
        }
        if (req.getCostPrice() != null) {
            if (req.getCostPrice().signum() < 0) {
                throw new IllegalArgumentException("成本价不能为负数");
            }
            cr.setCostPrice(req.getCostPrice());
        }
        if (req.getCurrency() != null && !req.getCurrency().isBlank()) {
            cr.setCurrency(Currency.valueOf(req.getCurrency().toUpperCase()));
        }
        if (req.getEffectiveDate() != null) {
            cr.setEffectiveDate(req.getEffectiveDate());
        }
        if (req.getDescription() != null) {
            cr.setDescription(req.getDescription());
        }
    }

    /**
     * 可见性校验（委托 DataVisibilityChecker）
     */
    private void checkVisibility(CommercialRecord cr, User user) {
        if (dataVisibilityChecker.canAccess(user, cr.getOwner(), cr.getConfidentialityLevel())) {
            return;
        }
        throw new SecurityException("无权访问该成本记录");
    }

    private String resolveAccessRole(CommercialRecord cr, User currentUser) {
        if (dataVisibilityChecker.isAdmin(currentUser)) {
            return "admin";
        }
        if (cr.getOwner() != null && cr.getOwner().getId().equals(currentUser.getId())) {
            return "owner";
        }
        if (dataVisibilityChecker.isDeptLeader(currentUser)) {
            return "leader";
        }
        return "viewer";
    }

    private CommercialRecordListDto toListDto(CommercialRecord cr, User currentUser) {
        CommercialRecordListDto dto = new CommercialRecordListDto();
        dto.setId(cr.getId());
        dto.setItemName(cr.getItemName());
        dto.setCostPrice(cr.getCostPrice());
        dto.setCurrency(cr.getCurrency() != null ? cr.getCurrency().name() : null);
        dto.setEffectiveDate(cr.getEffectiveDate());
        dto.setConfidentialityLevel(cr.getConfidentialityLevel() != null
                ? cr.getConfidentialityLevel().name() : null);
        dto.setSupplierId(cr.getSupplier() != null ? cr.getSupplier().getId() : null);
        dto.setSupplierCode(cr.getSupplier() != null ? cr.getSupplier().getSupplierCode() : null);
        dto.setSupplierName(cr.getSupplier() != null ? cr.getSupplier().getName() : null);
        dto.setOwnerId(cr.getOwner() != null ? cr.getOwner().getId() : null);
        dto.setOwnerName(cr.getOwner() != null ? cr.getOwner().getRealName() : null);
        dto.setCreatedAt(cr.getCreatedAt());
        dto.setAccessRole(resolveAccessRole(cr, currentUser));
        return dto;
    }

    private CommercialRecordDetailDto toDetailDto(CommercialRecord cr, User currentUser) {
        CommercialRecordDetailDto dto = new CommercialRecordDetailDto();
        dto.setId(cr.getId());
        dto.setItemName(cr.getItemName());
        dto.setCostPrice(cr.getCostPrice());
        dto.setCurrency(cr.getCurrency() != null ? cr.getCurrency().name() : null);
        dto.setEffectiveDate(cr.getEffectiveDate());
        dto.setConfidentialityLevel(cr.getConfidentialityLevel() != null
                ? cr.getConfidentialityLevel().name() : null);
        dto.setDescription(cr.getDescription());
        dto.setSupplierId(cr.getSupplier() != null ? cr.getSupplier().getId() : null);
        dto.setSupplierCode(cr.getSupplier() != null ? cr.getSupplier().getSupplierCode() : null);
        dto.setSupplierName(cr.getSupplier() != null ? cr.getSupplier().getName() : null);
        dto.setOwnerId(cr.getOwner() != null ? cr.getOwner().getId() : null);
        dto.setOwnerName(cr.getOwner() != null ? cr.getOwner().getRealName() : null);
        dto.setOwnerDepartmentName(cr.getOwner() != null && cr.getOwner().getDepartment() != null
                ? cr.getOwner().getDepartment().getName() : null);
        dto.setOptimisticLockVersion(cr.getOptimisticLockVersion());
        dto.setCreatedAt(cr.getCreatedAt());
        dto.setUpdatedAt(cr.getUpdatedAt());
        dto.setAccessRole(resolveAccessRole(cr, currentUser));
        return dto;
    }

    /**
     * 构建动态查询条件（同 ResearchData 模式）
     */
    private Specification<CommercialRecord> buildSpecification(Long supplierId, String keyword,
                                                                 String confidentialityLevel, String view,
                                                                 User currentUser) {
        return (root, query, cb) -> {
            List<Predicate> predicates = new ArrayList<>();

            // 可见范围（委托 DataVisibilityChecker）
            String v = dataVisibilityChecker.resolveView(view, currentUser);
            if ("all".equals(v)) {
                // ADMIN 全见，不加可见性过滤
            } else if ("mine".equals(v)) {
                predicates.add(cb.equal(root.get("owner").get("id"), currentUser.getId()));
            } else if ("public".equals(v)) {
                predicates.add(cb.equal(root.get("confidentialityLevel"),
                        ConfidentialityLevel.PUBLIC));
            } else {
                // 默认：统一可见性规则（owner + 同部门 + allowedLevels）
                predicates.add(dataVisibilityChecker.buildVisibilityPredicate(
                        root, query, cb, currentUser));
            }

            // 供应商
            if (supplierId != null) {
                predicates.add(cb.equal(root.get("supplier").get("id"), supplierId));
            }
            // 保密等级
            if (confidentialityLevel != null && !confidentialityLevel.isBlank()) {
                predicates.add(cb.equal(root.get("confidentialityLevel"),
                        ConfidentialityLevel.valueOf(confidentialityLevel.toUpperCase())));
            }
            // 关键词（itemName 或 description 模糊匹配）
            if (keyword != null && !keyword.isBlank()) {
                String like = "%" + keyword + "%";
                Predicate nameLike = cb.like(root.get("itemName"), like);
                Predicate descLike = cb.like(root.get("description"), like);
                predicates.add(cb.or(nameLike, descLike));
            }

            return cb.and(predicates.toArray(new Predicate[0]));
        };
    }
}
