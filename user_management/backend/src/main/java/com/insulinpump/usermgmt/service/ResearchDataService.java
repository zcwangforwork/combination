package com.insulinpump.usermgmt.service;

import com.insulinpump.usermgmt.dto.ResearchDataDetailDto;
import com.insulinpump.usermgmt.dto.ResearchDataListDto;
import com.insulinpump.usermgmt.dto.ResearchDataRequest;
import com.insulinpump.usermgmt.model.*;
import com.insulinpump.usermgmt.repository.DocumentCategoryRepository;
import com.insulinpump.usermgmt.repository.ResearchDataRepository;
import jakarta.persistence.criteria.Predicate;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.data.jpa.domain.Specification;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * 研发数据 Service（结构化记录，区别于 DocumentService 的文件存储）
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
 * 保密等级：复用 4 级体系（PUBLIC/INTERNAL/CONFIDENTIAL/TOP_SECRET）
 *
 * paramCategory 子分类（仅 DESIGN_PARAM 类型使用）：
 *   - FACTORY_MEASURED    : 工厂实测值
 *   - EXTERNAL_TECHNICAL  : 对外技术参数
 *   - COMMON              : 常规常见参数
 * 存储在 extraData.paramCategory（JSONB），由 Service 层注入/校验。
 */
@Service
public class ResearchDataService {

    /** DESIGN_PARAM 类型可用的参数子分类 */
    private static final Set<String> VALID_PARAM_CATEGORIES = Set.of(
            "FACTORY_MEASURED", "EXTERNAL_TECHNICAL", "COMMON"
    );

    private final ResearchDataRepository researchDataRepository;
    private final DocumentCategoryRepository categoryRepository;
    private final DataVisibilityChecker dataVisibilityChecker;

    public ResearchDataService(ResearchDataRepository researchDataRepository,
                                DocumentCategoryRepository categoryRepository,
                                DataVisibilityChecker dataVisibilityChecker) {
        this.researchDataRepository = researchDataRepository;
        this.categoryRepository = categoryRepository;
        this.dataVisibilityChecker = dataVisibilityChecker;
    }

    // ============ 查询 ============

    /**
     * 分页查询研发数据
     *
     * @param view "mine"=我的 / "all"=全部(仅ADMIN) / "public"=全员可见 / 其他=mine∪public
     * @param paramCategory 参数子分类（仅 DESIGN_PARAM 类型有意义）
     */
    @Transactional(readOnly = true)
    public Page<ResearchDataListDto> list(int page, int size,
                                           String recordType, Long categoryId,
                                           String keyword, String confidentialityLevel,
                                           String paramCategory,
                                           String view, User currentUser) {
        Specification<ResearchData> spec = buildSpecification(
                recordType, categoryId, keyword, confidentialityLevel, paramCategory,
                view, currentUser);

        PageRequest pageable = PageRequest.of(page, size,
                Sort.by(Sort.Direction.DESC, "createdAt"));

        Page<ResearchData> pageResult = researchDataRepository.findAll(spec, pageable);
        return pageResult.map(d -> toListDto(d, currentUser));
    }

    /**
     * 研发数据详情
     */
    @Transactional(readOnly = true)
    public ResearchDataDetailDto getById(Long id, User currentUser) {
        ResearchData rd = researchDataRepository.findById(id)
                .orElseThrow(() -> new IllegalArgumentException("研发数据不存在"));
        checkVisibility(rd, currentUser);
        return toDetailDto(rd, currentUser);
    }

    // ============ 写操作 ============

    /**
     * 创建研发数据
     * 权限：任意已登录用户
     */
    @Transactional
    public ResearchDataDetailDto create(ResearchDataRequest req, User currentUser) {
        if (req.getRecordType() == null || req.getRecordType().isBlank()) {
            throw new IllegalArgumentException("记录类型不能为空");
        }
        if (req.getTitle() == null || req.getTitle().isBlank()) {
            throw new IllegalArgumentException("标题不能为空");
        }

        ResearchData rd = new ResearchData();
        rd.setRecordType(ResearchDataType.valueOf(req.getRecordType().toUpperCase()));
        rd.setRecordNo(req.getRecordNo());
        rd.setTitle(req.getTitle());
        rd.setRecordDate(req.getRecordDate());
        rd.setOperator(req.getOperator());
        if (req.getStatus() != null && !req.getStatus().isBlank()) {
            rd.setStatus(ResearchDataStatus.valueOf(req.getStatus().toUpperCase()));
        }
        rd.setDeviceModel(req.getDeviceModel());
        rd.setBatchNo(req.getBatchNo());

        // 保密等级（默认 INTERNAL）
        ConfidentialityLevel level = ConfidentialityLevel.INTERNAL;
        if (req.getConfidentialityLevel() != null && !req.getConfidentialityLevel().isBlank()) {
            level = ConfidentialityLevel.valueOf(req.getConfidentialityLevel().toUpperCase());
        }
        rd.setConfidentialityLevel(level);

        rd.setDescription(req.getDescription());
        rd.setExtraData(injectParamCategory(req.getExtraData(), req.getParamCategory(), req.getRecordType()));

        if (req.getCategoryId() != null) {
            DocumentCategory category = categoryRepository.findById(req.getCategoryId())
                    .orElseThrow(() -> new IllegalArgumentException("分类不存在"));
            if (category.getDocType() != DocumentType.RESEARCH) {
                throw new IllegalArgumentException("分类不属于研发资料");
            }
            rd.setCategory(category);
        }

        rd.setOwner(currentUser);

        ResearchData saved = researchDataRepository.save(rd);
        return toDetailDto(saved, currentUser);
    }

    /**
     * 更新研发数据（部分更新）
     * 权限：owner 或 ADMIN
     */
    @Transactional
    public ResearchDataDetailDto update(Long id, ResearchDataRequest req, User currentUser) {
        ResearchData rd = researchDataRepository.findById(id)
                .orElseThrow(() -> new IllegalArgumentException("研发数据不存在"));
        if (!dataVisibilityChecker.canModify(currentUser, rd.getOwner(),
                rd.getConfidentialityLevel(), rd.getCategory(), true)) {
            throw new SecurityException("无权修改该研发数据");
        }

        if (req.getRecordType() != null && !req.getRecordType().isBlank()) {
            rd.setRecordType(ResearchDataType.valueOf(req.getRecordType().toUpperCase()));
        }
        if (req.getRecordNo() != null) {
            rd.setRecordNo(req.getRecordNo());
        }
        if (req.getTitle() != null && !req.getTitle().isBlank()) {
            rd.setTitle(req.getTitle());
        }
        if (req.getRecordDate() != null) {
            rd.setRecordDate(req.getRecordDate());
        }
        if (req.getOperator() != null) {
            rd.setOperator(req.getOperator());
        }
        if (req.getStatus() != null && !req.getStatus().isBlank()) {
            rd.setStatus(ResearchDataStatus.valueOf(req.getStatus().toUpperCase()));
        }
        if (req.getDeviceModel() != null) {
            rd.setDeviceModel(req.getDeviceModel());
        }
        if (req.getBatchNo() != null) {
            rd.setBatchNo(req.getBatchNo());
        }
        if (req.getConfidentialityLevel() != null && !req.getConfidentialityLevel().isBlank()) {
            rd.setConfidentialityLevel(
                    ConfidentialityLevel.valueOf(req.getConfidentialityLevel().toUpperCase()));
        }
        if (req.getDescription() != null) {
            rd.setDescription(req.getDescription());
        }
        if (req.getExtraData() != null || req.getParamCategory() != null) {
            // 部分更新：合并现有 extraData 与新传入的 paramCategory
            Map<String, Object> merged = rd.getExtraData();
            if (merged == null) {
                merged = new java.util.HashMap<>();
            } else {
                merged = new java.util.HashMap<>(merged);
            }
            if (req.getExtraData() != null) {
                merged.putAll(req.getExtraData());
            }
            String mergedRecordType = req.getRecordType() != null && !req.getRecordType().isBlank()
                    ? req.getRecordType() : rd.getRecordType().name();
            rd.setExtraData(injectParamCategory(merged, req.getParamCategory(), mergedRecordType));
        }
        if (req.getCategoryId() != null) {
            DocumentCategory category = categoryRepository.findById(req.getCategoryId())
                    .orElseThrow(() -> new IllegalArgumentException("分类不存在"));
            if (category.getDocType() != DocumentType.RESEARCH) {
                throw new IllegalArgumentException("分类不属于研发资料");
            }
            rd.setCategory(category);
        }

        ResearchData saved = researchDataRepository.save(rd);
        return toDetailDto(saved, currentUser);
    }

    /**
     * 删除研发数据
     * 权限：owner 或 ADMIN
     */
    @Transactional
    public void delete(Long id, User currentUser) {
        ResearchData rd = researchDataRepository.findById(id)
                .orElseThrow(() -> new IllegalArgumentException("研发数据不存在"));
        if (!dataVisibilityChecker.canModify(currentUser, rd.getOwner(),
                rd.getConfidentialityLevel(), rd.getCategory(), true)) {
            throw new SecurityException("无权删除该研发数据");
        }
        researchDataRepository.delete(rd);
    }

    // ============ 私有辅助方法 ============

    /**
     * 可见性校验（委托 DataVisibilityChecker 5-arg，启用 category grant）
     */
    private void checkVisibility(ResearchData rd, User user) {
        if (dataVisibilityChecker.canAccess(user, rd.getOwner(), rd.getConfidentialityLevel(),
                rd.getCategory(), true)) {
            return;
        }
        throw new SecurityException("无权访问该研发数据");
    }

    /**
     * 解析访问角色
     *   - admin: ADMIN
     *   - owner: 我的记录
     *   - leader: 部门负责人（本部门他人记录）
     *   - viewer: 仅可查看（被授权等级）
     */
    private String resolveAccessRole(ResearchData rd, User currentUser) {
        if (dataVisibilityChecker.isAdmin(currentUser)) {
            return "admin";
        }
        if (rd.getOwner() != null && rd.getOwner().getId().equals(currentUser.getId())) {
            return "owner";
        }
        if (dataVisibilityChecker.isDeptLeader(currentUser)) {
            return "leader";
        }
        return "viewer";
    }

    /**
     * 注入 paramCategory 到 extraData JSONB，并校验：
     *   - 当 recordType=DESIGN_PARAM 且 paramCategory 非空：校验取值合法
     *   - 当 recordType=DESIGN_PARAM 且 paramCategory 为空：允许（paramCategory 非必填，仅前端筛选用）
     *   - 当 recordType≠DESIGN_PARAM 且 paramCategory 非空：抛错（字段不适用）
     *   - 当 paramCategory 为空：不修改 extraData
     */
    private Map<String, Object> injectParamCategory(Map<String, Object> extraData,
                                                     String paramCategory, String recordType) {
        Map<String, Object> result = extraData != null
                ? new java.util.HashMap<>(extraData)
                : new java.util.HashMap<>();

        if (paramCategory == null || paramCategory.isBlank()) {
            return result;
        }

        String upper = paramCategory.toUpperCase();
        boolean isDesignParam = recordType != null
                && "DESIGN_PARAM".equalsIgnoreCase(recordType);

        if (!isDesignParam) {
            throw new IllegalArgumentException(
                    "paramCategory 仅适用于 DESIGN_PARAM 类型，当前类型: " + recordType);
        }
        if (!VALID_PARAM_CATEGORIES.contains(upper)) {
            throw new IllegalArgumentException(
                    "无效的 paramCategory: " + paramCategory
                            + "，可选值: " + VALID_PARAM_CATEGORIES);
        }

        result.put("paramCategory", upper);
        return result;
    }

    private ResearchDataListDto toListDto(ResearchData rd, User currentUser) {
        ResearchDataListDto dto = new ResearchDataListDto();
        dto.setId(rd.getId());
        dto.setRecordType(rd.getRecordType() != null ? rd.getRecordType().name() : null);
        dto.setRecordNo(rd.getRecordNo());
        dto.setTitle(rd.getTitle());
        dto.setRecordDate(rd.getRecordDate());
        dto.setOperator(rd.getOperator());
        dto.setStatus(rd.getStatus() != null ? rd.getStatus().name() : null);
        dto.setDeviceModel(rd.getDeviceModel());
        dto.setBatchNo(rd.getBatchNo());
        dto.setConfidentialityLevel(rd.getConfidentialityLevel() != null
                ? rd.getConfidentialityLevel().name() : null);
        dto.setParamCategory(extractParamCategory(rd.getExtraData()));
        dto.setCategoryId(rd.getCategory() != null ? rd.getCategory().getId() : null);
        dto.setCategoryName(rd.getCategory() != null ? rd.getCategory().getName() : null);
        dto.setOwnerId(rd.getOwner() != null ? rd.getOwner().getId() : null);
        dto.setOwnerName(rd.getOwner() != null ? rd.getOwner().getRealName() : null);
        dto.setOwnerDepartmentName(rd.getOwner() != null && rd.getOwner().getDepartment() != null
                ? rd.getOwner().getDepartment().getName() : null);
        dto.setCreatedAt(rd.getCreatedAt());
        dto.setAccessRole(resolveAccessRole(rd, currentUser));
        return dto;
    }

    private ResearchDataDetailDto toDetailDto(ResearchData rd, User currentUser) {
        ResearchDataDetailDto dto = new ResearchDataDetailDto();
        dto.setId(rd.getId());
        dto.setRecordType(rd.getRecordType() != null ? rd.getRecordType().name() : null);
        dto.setRecordNo(rd.getRecordNo());
        dto.setTitle(rd.getTitle());
        dto.setRecordDate(rd.getRecordDate());
        dto.setOperator(rd.getOperator());
        dto.setStatus(rd.getStatus() != null ? rd.getStatus().name() : null);
        dto.setDeviceModel(rd.getDeviceModel());
        dto.setBatchNo(rd.getBatchNo());
        dto.setConfidentialityLevel(rd.getConfidentialityLevel() != null
                ? rd.getConfidentialityLevel().name() : null);
        dto.setDescription(rd.getDescription());
        dto.setParamCategory(extractParamCategory(rd.getExtraData()));
        dto.setExtraData(rd.getExtraData());
        dto.setCategoryId(rd.getCategory() != null ? rd.getCategory().getId() : null);
        dto.setCategoryName(rd.getCategory() != null ? rd.getCategory().getName() : null);
        dto.setCategoryCode(rd.getCategory() != null ? rd.getCategory().getCode() : null);
        dto.setOwnerId(rd.getOwner() != null ? rd.getOwner().getId() : null);
        dto.setOwnerName(rd.getOwner() != null ? rd.getOwner().getRealName() : null);
        dto.setOwnerDepartmentName(rd.getOwner() != null && rd.getOwner().getDepartment() != null
                ? rd.getOwner().getDepartment().getName() : null);
        dto.setCreatedAt(rd.getCreatedAt());
        dto.setUpdatedAt(rd.getUpdatedAt());
        dto.setAccessRole(resolveAccessRole(rd, currentUser));
        return dto;
    }

    /**
     * 从 extraData JSONB 提取 paramCategory 字段值
     */
    private String extractParamCategory(Map<String, Object> extraData) {
        if (extraData == null) {
            return null;
        }
        Object val = extraData.get("paramCategory");
        return val != null ? val.toString() : null;
    }

    /**
     * 构建动态查询条件
     *
     * view 参数决定可见范围：
     *   "mine"   : owner = currentUser（看自己所有等级）
     *   "all"    : 仅 ADMIN，看全部
     *   "public" : confidentialityLevel = PUBLIC
     *   其他/默认: (owner = currentUser) OR (confidentialityLevel = PUBLIC)
     *
     * paramCategory 过滤：使用 PostgreSQL jsonb_extract_path_text 函数
     *   （功能索引支持：CREATE INDEX ... ON t_research_data ((extraData->>'paramCategory'))）
     */
    private Specification<ResearchData> buildSpecification(String recordType, Long categoryId,
                                                            String keyword, String confidentialityLevel,
                                                            String paramCategory,
                                                            String view, User currentUser) {
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
                // 默认：统一可见性规则（owner + 同部门 + allowedLevels + category grant）
                predicates.add(dataVisibilityChecker.buildVisibilityPredicate(
                        root, query, cb, currentUser, true));
            }

            // 记录类型
            if (recordType != null && !recordType.isBlank()) {
                predicates.add(cb.equal(root.get("recordType"),
                        ResearchDataType.valueOf(recordType.toUpperCase())));
            }
            // 分类
            if (categoryId != null) {
                predicates.add(cb.equal(root.get("category").get("id"), categoryId));
            }
            // 保密等级
            if (confidentialityLevel != null && !confidentialityLevel.isBlank()) {
                predicates.add(cb.equal(root.get("confidentialityLevel"),
                        ConfidentialityLevel.valueOf(confidentialityLevel.toUpperCase())));
            }
            // 参数子分类（JSONB 字段过滤）
            if (paramCategory != null && !paramCategory.isBlank()) {
                predicates.add(cb.equal(
                        cb.function("jsonb_extract_path_text", String.class,
                                root.get("extraData"),
                                cb.literal("paramCategory")),
                        paramCategory.toUpperCase()));
            }
            // 关键词（title 或 recordNo 模糊匹配）
            if (keyword != null && !keyword.isBlank()) {
                String like = "%" + keyword + "%";
                Predicate titleLike = cb.like(root.get("title"), like);
                Predicate noLike = cb.like(root.get("recordNo"), like);
                predicates.add(cb.or(titleLike, noLike));
            }

            return cb.and(predicates.toArray(new Predicate[0]));
        };
    }
}
