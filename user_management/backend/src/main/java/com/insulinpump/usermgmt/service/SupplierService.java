package com.insulinpump.usermgmt.service;

import com.insulinpump.usermgmt.dto.SupplierDetailDto;
import com.insulinpump.usermgmt.dto.SupplierListDto;
import com.insulinpump.usermgmt.dto.SupplierRequest;
import com.insulinpump.usermgmt.model.QualificationStatus;
import com.insulinpump.usermgmt.model.Supplier;
import com.insulinpump.usermgmt.model.User;
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
 * 供应商 Service（主数据风格）
 *
 * 可见性：所有登录用户可见（含 enabled=false 的停用记录，保留历史供应商名）
 * 编辑/删除权限：仅 ADMIN
 * 软删除：通过 enabled=false 实现（保留 FK 引用，不破坏 CommercialRecord 历史）
 *
 * 乐观锁：基于 @Version 字段，更新时校验 optimisticLockVersion
 */
@Service
public class SupplierService {

    private final SupplierRepository supplierRepository;

    public SupplierService(SupplierRepository supplierRepository) {
        this.supplierRepository = supplierRepository;
    }

    // ============ 查询 ============

    /**
     * 分页查询供应商
     *
     * @param includeDisabled 是否包含已停用记录（默认 true：主数据风格，历史供应商需可见）
     */
    @Transactional(readOnly = true)
    public Page<SupplierListDto> list(int page, int size,
                                       String category, String qualificationStatus,
                                       String keyword, Boolean includeDisabled,
                                       User currentUser) {
        Specification<Supplier> spec = buildSpecification(
                category, qualificationStatus, keyword, includeDisabled);

        PageRequest pageable = PageRequest.of(page, size,
                Sort.by(Sort.Direction.DESC, "createdAt"));

        Page<Supplier> pageResult = supplierRepository.findAll(spec, pageable);
        return pageResult.map(this::toListDto);
    }

    @Transactional(readOnly = true)
    public SupplierDetailDto getById(Long id) {
        Supplier s = supplierRepository.findById(id)
                .orElseThrow(() -> new IllegalArgumentException("供应商不存在"));
        return toDetailDto(s);
    }

    /** 下拉选择用：所有启用的供应商（按名称排序） */
    @Transactional(readOnly = true)
    public List<SupplierListDto> listEnabled() {
        Specification<Supplier> spec = (root, query, cb) ->
                cb.isTrue(root.get("enabled"));
        return supplierRepository.findAll(spec, Sort.by(Sort.Direction.ASC, "name"))
                .stream().map(this::toListDto).toList();
    }

    // ============ 写操作 ============

    /**
     * 创建供应商
     * 权限：仅 ADMIN（在 Controller 层 @PreAuthorize 控制）
     */
    @Transactional
    public SupplierDetailDto create(SupplierRequest req, User currentUser) {
        validateRequest(req, true);

        if (supplierRepository.findBySupplierCode(req.getSupplierCode()).isPresent()) {
            throw new IllegalArgumentException("供应商编码已存在: " + req.getSupplierCode());
        }

        Supplier s = new Supplier();
        applyRequestToEntity(s, req);

        Supplier saved = supplierRepository.save(s);
        return toDetailDto(saved);
    }

    /**
     * 更新供应商（部分更新）
     * 权限：仅 ADMIN
     * 乐观锁：必须传 optimisticLockVersion
     */
    @Transactional
    public SupplierDetailDto update(Long id, SupplierRequest req, User currentUser) {
        Supplier s = supplierRepository.findById(id)
                .orElseThrow(() -> new IllegalArgumentException("供应商不存在"));

        if (req.getOptimisticLockVersion() == null) {
            throw new IllegalArgumentException("缺少乐观锁版本号 optimisticLockVersion");
        }
        // JPA @Version 自动校验，触发 ObjectOptimisticLockingFailureException
        s.setOptimisticLockVersion(req.getOptimisticLockVersion());

        validateRequest(req, false);

        // 编码唯一性校验（排除自身）
        if (req.getSupplierCode() != null && !req.getSupplierCode().isBlank()) {
            if (supplierRepository.existsBySupplierCodeAndIdNot(req.getSupplierCode(), id)) {
                throw new IllegalArgumentException("供应商编码已存在: " + req.getSupplierCode());
            }
            s.setSupplierCode(req.getSupplierCode());
        }

        applyRequestToEntity(s, req);

        try {
            Supplier saved = supplierRepository.save(s);
            return toDetailDto(saved);
        } catch (ObjectOptimisticLockingFailureException e) {
            throw new IllegalArgumentException("该供应商已被其他用户修改，请刷新后重试");
        }
    }

    /**
     * 软删除供应商（enabled=false）
     * 权限：仅 ADMIN
     * 不删除记录，保留 FK 引用历史
     */
    @Transactional
    public void disable(Long id, User currentUser) {
        Supplier s = supplierRepository.findById(id)
                .orElseThrow(() -> new IllegalArgumentException("供应商不存在"));
        s.setEnabled(false);
        supplierRepository.save(s);
    }

    /**
     * 恢复已停用的供应商（enabled=true）
     * 权限：仅 ADMIN
     */
    @Transactional
    public void enable(Long id, User currentUser) {
        Supplier s = supplierRepository.findById(id)
                .orElseThrow(() -> new IllegalArgumentException("供应商不存在"));
        s.setEnabled(true);
        supplierRepository.save(s);
    }

    // ============ 私有辅助方法 ============

    private void validateRequest(SupplierRequest req, boolean isCreate) {
        if (isCreate) {
            if (req.getSupplierCode() == null || req.getSupplierCode().isBlank()) {
                throw new IllegalArgumentException("供应商编码不能为空");
            }
            if (req.getName() == null || req.getName().isBlank()) {
                throw new IllegalArgumentException("供应商名称不能为空");
            }
        }
        if (req.getQualificationStatus() != null && !req.getQualificationStatus().isBlank()) {
            try {
                QualificationStatus.valueOf(req.getQualificationStatus().toUpperCase());
            } catch (IllegalArgumentException e) {
                throw new IllegalArgumentException("无效的合格状态: " + req.getQualificationStatus());
            }
        }
    }

    private void applyRequestToEntity(Supplier s, SupplierRequest req) {
        if (req.getSupplierCode() != null && !req.getSupplierCode().isBlank()) {
            s.setSupplierCode(req.getSupplierCode());
        }
        if (req.getName() != null && !req.getName().isBlank()) {
            s.setName(req.getName());
        }
        if (req.getContact() != null) {
            s.setContact(req.getContact());
        }
        if (req.getPhone() != null) {
            s.setPhone(req.getPhone());
        }
        if (req.getEmail() != null) {
            s.setEmail(req.getEmail());
        }
        if (req.getCategory() != null) {
            s.setCategory(req.getCategory());
        }
        if (req.getQualificationStatus() != null && !req.getQualificationStatus().isBlank()) {
            s.setQualificationStatus(
                    QualificationStatus.valueOf(req.getQualificationStatus().toUpperCase()));
        }
        if (req.getQualityContactName() != null) {
            s.setQualityContactName(req.getQualityContactName());
        }
        if (req.getQualityContactPhone() != null) {
            s.setQualityContactPhone(req.getQualityContactPhone());
        }
        if (req.getEnabled() != null) {
            s.setEnabled(req.getEnabled());
        }
    }

    private Specification<Supplier> buildSpecification(String category, String qualificationStatus,
                                                        String keyword, Boolean includeDisabled) {
        return (root, query, cb) -> {
            List<Predicate> predicates = new ArrayList<>();

            // 是否包含停用记录（默认包含，主数据风格）
            if (Boolean.FALSE.equals(includeDisabled)) {
                predicates.add(cb.isTrue(root.get("enabled")));
            }

            // 分类
            if (category != null && !category.isBlank()) {
                predicates.add(cb.equal(root.get("category"), category));
            }
            // 合格状态
            if (qualificationStatus != null && !qualificationStatus.isBlank()) {
                predicates.add(cb.equal(root.get("qualificationStatus"),
                        QualificationStatus.valueOf(qualificationStatus.toUpperCase())));
            }
            // 关键词（supplierCode 或 name 模糊匹配）
            if (keyword != null && !keyword.isBlank()) {
                String like = "%" + keyword + "%";
                Predicate codeLike = cb.like(root.get("supplierCode"), like);
                Predicate nameLike = cb.like(root.get("name"), like);
                predicates.add(cb.or(codeLike, nameLike));
            }

            return cb.and(predicates.toArray(new Predicate[0]));
        };
    }

    private SupplierListDto toListDto(Supplier s) {
        SupplierListDto dto = new SupplierListDto();
        dto.setId(s.getId());
        dto.setSupplierCode(s.getSupplierCode());
        dto.setName(s.getName());
        dto.setContact(s.getContact());
        dto.setPhone(s.getPhone());
        dto.setEmail(s.getEmail());
        dto.setCategory(s.getCategory());
        dto.setQualificationStatus(s.getQualificationStatus() != null
                ? s.getQualificationStatus().name() : null);
        dto.setQualityContactName(s.getQualityContactName());
        dto.setQualityContactPhone(s.getQualityContactPhone());
        dto.setEnabled(s.getEnabled());
        dto.setCreatedAt(s.getCreatedAt());
        dto.setUpdatedAt(s.getUpdatedAt());
        return dto;
    }

    private SupplierDetailDto toDetailDto(Supplier s) {
        SupplierDetailDto dto = new SupplierDetailDto();
        dto.setId(s.getId());
        dto.setSupplierCode(s.getSupplierCode());
        dto.setName(s.getName());
        dto.setContact(s.getContact());
        dto.setPhone(s.getPhone());
        dto.setEmail(s.getEmail());
        dto.setCategory(s.getCategory());
        dto.setQualificationStatus(s.getQualificationStatus() != null
                ? s.getQualificationStatus().name() : null);
        dto.setQualityContactName(s.getQualityContactName());
        dto.setQualityContactPhone(s.getQualityContactPhone());
        dto.setEnabled(s.getEnabled());
        dto.setOptimisticLockVersion(s.getOptimisticLockVersion());
        dto.setCreatedAt(s.getCreatedAt());
        dto.setUpdatedAt(s.getUpdatedAt());
        return dto;
    }
}
