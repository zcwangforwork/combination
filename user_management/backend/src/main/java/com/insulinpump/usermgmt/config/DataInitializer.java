package com.insulinpump.usermgmt.config;

import com.insulinpump.usermgmt.model.Department;
import com.insulinpump.usermgmt.model.DocumentCategory;
import com.insulinpump.usermgmt.model.DocumentType;
import com.insulinpump.usermgmt.model.QualificationStatus;
import com.insulinpump.usermgmt.model.Role;
import com.insulinpump.usermgmt.model.Supplier;
import com.insulinpump.usermgmt.model.User;
import com.insulinpump.usermgmt.repository.DepartmentRepository;
import com.insulinpump.usermgmt.repository.DocumentCategoryRepository;
import com.insulinpump.usermgmt.repository.RoleRepository;
import com.insulinpump.usermgmt.repository.SupplierRepository;
import com.insulinpump.usermgmt.repository.UserRepository;
import org.springframework.boot.CommandLineRunner;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Component;

import java.util.*;

/**
 * 数据初始化器
 *
 *  - 首次启动：创建角色、部门、管理员、示例员工、文档分类
 *  - 已有数据：补全新增的文档权限到现有角色（幂等升级）
 */
@Component
public class DataInitializer implements CommandLineRunner {

    private final RoleRepository roleRepository;
    private final DepartmentRepository departmentRepository;
    private final UserRepository userRepository;
    private final DocumentCategoryRepository categoryRepository;
    private final SupplierRepository supplierRepository;
    private final PasswordEncoder passwordEncoder;

    public DataInitializer(RoleRepository roleRepository,
                           DepartmentRepository departmentRepository,
                           UserRepository userRepository,
                           DocumentCategoryRepository categoryRepository,
                           SupplierRepository supplierRepository,
                           PasswordEncoder passwordEncoder) {
        this.roleRepository = roleRepository;
        this.departmentRepository = departmentRepository;
        this.userRepository = userRepository;
        this.categoryRepository = categoryRepository;
        this.supplierRepository = supplierRepository;
        this.passwordEncoder = passwordEncoder;
    }

    @Override
    public void run(String... args) {
        // 1. 首次启动：初始化角色/部门/用户
        if (roleRepository.count() == 0) {
            initializeRolesDepartmentsUsers();
        }

        // 2. 幂等升级：为现有角色补全文档权限（已存在数据库时执行）
        upgradeRolePermissions();

        // 3. 幂等升级：为现有部门设置 leader_id（已存在数据库时执行，新增字段）
        upgradeDepartmentLeaders();

        // 4. 幂等初始化：文档分类（已存在则跳过）
        initializeDocumentCategories();

        // 5. 幂等初始化：供应商主数据（示例种子数据，仅首次创建）
        initializeSuppliers();
    }

    /**
     * 首次启动：创建角色、部门、用户
     */
    private void initializeRolesDepartmentsUsers() {
        // 1. Create roles (含文档权限)
        Map<String, Role> roleMap = new LinkedHashMap<>();

        Role admin = createRole("系统管理员", "ADMIN", "拥有系统全部权限",
                "employee:read", "employee:write", "employee:delete",
                "dashboard:read", "department:read",
                "doc:read", "doc:write", "doc:delete",
                "doc:approve", "doc:reject", "doc:retire",
                "supplier:read", "supplier:write", "supplier:delete",
                "commercial:read", "commercial:write", "commercial:delete",
                "user:assign-confidentiality", "user:assign-category", "user:assign-document",
                "notification:publish");
        roleMap.put("ADMIN", admin);

        Role structuralEng = createRole("结构工程师", "STRUCTURAL_ENGINEER",
                "负责胰岛素泵结构设计",
                "employee:read", "dashboard:read", "doc:read",
                "supplier:read", "commercial:read", "commercial:write", "commercial:delete");
        roleMap.put("STRUCTURAL_ENGINEER", structuralEng);

        Role circuitEng = createRole("电路工程师", "CIRCUIT_ENGINEER",
                "负责电路原理图设计和PCB Layout",
                "employee:read", "dashboard:read", "doc:read",
                "supplier:read", "commercial:read", "commercial:write", "commercial:delete");
        roleMap.put("CIRCUIT_ENGINEER", circuitEng);

        Role testEng = createRole("测试工程师", "TEST_ENGINEER",
                "负责产品测试验证",
                "employee:read", "dashboard:read", "doc:read",
                "supplier:read", "commercial:read", "commercial:write", "commercial:delete");
        roleMap.put("TEST_ENGINEER", testEng);

        Role systemEng = createRole("体系工程师", "SYSTEM_ENGINEER",
                "负责质量管理体系建设",
                "employee:read", "dashboard:read", "doc:read", "doc:write",
                "supplier:read", "commercial:read", "commercial:write", "commercial:delete");
        roleMap.put("SYSTEM_ENGINEER", systemEng);

        Role qualityEng = createRole("质量工程师", "QUALITY_ENGINEER",
                "负责产品质量控制和检验",
                "employee:read", "dashboard:read", "doc:read",
                "supplier:read", "commercial:read", "commercial:write", "commercial:delete");
        roleMap.put("QUALITY_ENGINEER", qualityEng);

        Role regulatoryEng = createRole("注册工程师", "REGULATORY_ENGINEER",
                "负责NMPA/CE/FDA注册申报",
                "employee:read", "dashboard:read", "doc:read",
                "supplier:read", "commercial:read", "commercial:write", "commercial:delete");
        roleMap.put("REGULATORY_ENGINEER", regulatoryEng);

        Role softwareEng = createRole("软件工程师", "SOFTWARE_ENGINEER",
                "负责嵌入式软件和App开发",
                "employee:read", "dashboard:read", "doc:read",
                "supplier:read", "commercial:read", "commercial:write", "commercial:delete");
        roleMap.put("SOFTWARE_ENGINEER", softwareEng);

        Role productionEng = createRole("生产工程师", "PRODUCTION_ENGINEER",
                "负责生产工艺和生产管理",
                "employee:read", "dashboard:read", "doc:read",
                "supplier:read", "commercial:read", "commercial:write", "commercial:delete");
        roleMap.put("PRODUCTION_ENGINEER", productionEng);

        // 2. Create departments
        Department rnd = createDept("研发中心", "负责产品研发和设计");
        Department struct = createDept("结构设计部", "机械结构设计");
        Department circuit = createDept("电路设计部", "硬件电路设计");
        Department software = createDept("软件开发部", "嵌入式软件与App");
        Department quality = createDept("质量部", "质量管理与控制");
        Department regulatory = createDept("注册部", "产品注册与法规事务");
        Department production = createDept("生产部", "产品生产与制造");
        Department systemDept = createDept("体系管理部", "质量管理体系");
        Department testing = createDept("测试验证部", "产品测试与验证");

        // 3. Create default admin user
        createUser("admin", "admin123", "系统管理员", "00001",
                "admin@insulinpump.com", "13800000000", admin, rnd);

        // 4. Create sample employees
        createUser("zhangsan", "123456", "张三", "00101",
                "zhangsan@insulinpump.com", "13800000001", structuralEng, struct);
        createUser("lisi", "123456", "李四", "00201",
                "lisi@insulinpump.com", "13800000002", circuitEng, circuit);
        createUser("wangwu", "123456", "王五", "00301",
                "wangwu@insulinpump.com", "13800000003", testEng, testing);
        createUser("zhaoliu", "123456", "赵六", "00401",
                "zhaoliu@insulinpump.com", "13800000004", systemEng, systemDept);
        createUser("sunqi", "123456", "孙七", "00501",
                "sunqi@insulinpump.com", "13800000005", qualityEng, quality);
        createUser("zhouba", "123456", "周八", "00601",
                "zhouba@insulinpump.com", "13800000006", regulatoryEng, regulatory);
        createUser("wujiu", "123456", "吴九", "00701",
                "wujiu@insulinpump.com", "13800000007", softwareEng, software);
        createUser("zhengshi", "123456", "郑十", "00801",
                "zhengshi@insulinpump.com", "13800000008", productionEng, production);

        // 5. 首次启动：设置部门负责人 leader_id
        setDepartmentLeaders();
    }

    /**
     * 幂等升级：为现有角色补全文档权限
     * 已存在数据库时执行，确保所有角色都有 doc:read，ADMIN 有 doc:write/delete，SYSTEM_ENGINEER 有 doc:write
     * 同时补全 supplier:read / commercial:read/write 权限
     */
    private void upgradeRolePermissions() {
        Map<String, Set<String>> rolePermissions = new HashMap<>();
        rolePermissions.put("ADMIN", new HashSet<>(Set.of(
                "doc:read", "doc:write", "doc:delete",
                "doc:approve", "doc:reject", "doc:retire",
                "supplier:read", "supplier:write", "supplier:delete",
                "commercial:read", "commercial:write", "commercial:delete")));
        rolePermissions.put("SYSTEM_ENGINEER", new HashSet<>(Set.of(
                "doc:read", "doc:write",
                "supplier:read", "commercial:read", "commercial:write", "commercial:delete")));
        // 其他角色：doc:read + supplier:read + commercial:read/write/delete（owner 模式）
        for (String code : List.of("STRUCTURAL_ENGINEER", "CIRCUIT_ENGINEER", "TEST_ENGINEER",
                "QUALITY_ENGINEER", "REGULATORY_ENGINEER", "SOFTWARE_ENGINEER", "PRODUCTION_ENGINEER")) {
            rolePermissions.put(code, new HashSet<>(Set.of(
                    "doc:read",
                    "supplier:read", "commercial:read", "commercial:write", "commercial:delete")));
        }

        for (Map.Entry<String, Set<String>> entry : rolePermissions.entrySet()) {
            roleRepository.findByCode(entry.getKey()).ifPresent(role -> {
                Set<String> perms = role.getPermissions();
                if (perms == null) {
                    perms = new HashSet<>();
                    role.setPermissions(perms);
                }
                boolean changed = perms.addAll(entry.getValue());
                if (changed) {
                    roleRepository.save(role);
                }
            });
        }

        // 幂等补全 ADMIN 的用户授权管理权限 + 文档审批权限
        roleRepository.findByCode("ADMIN").ifPresent(role -> {
            Set<String> perms = role.getPermissions();
            if (perms == null) {
                perms = new HashSet<>();
                role.setPermissions(perms);
            }
            boolean changed = false;
            if (perms.add("user:assign-confidentiality")) {
                changed = true;
            }
            if (perms.add("user:assign-category")) {
                changed = true;
            }
            if (perms.add("doc:approve")) {
                changed = true;
            }
            if (perms.add("doc:reject")) {
                changed = true;
            }
            if (perms.add("doc:retire")) {
                changed = true;
            }
            if (perms.add("notification:publish")) {
                changed = true;
            }
            if (perms.add("user:assign-document")) {
                changed = true;
            }
            if (changed) {
                roleRepository.save(role);
            }
        });
    }

    /**
     * 首次启动：设置部门负责人 leader_id
     *
     * 在 initializeRolesDepartmentsUsers 末尾调用，此时 Department 和 User 都已创建。
     */
    private void setDepartmentLeaders() {
        setLeaderIfAbsent("研发中心", "admin");
        setLeaderIfAbsent("结构设计部", "zhangsan");
        setLeaderIfAbsent("电路设计部", "lisi");
        setLeaderIfAbsent("测试验证部", "wangwu");
        setLeaderIfAbsent("体系管理部", "zhaoliu");
        setLeaderIfAbsent("质量部", "sunqi");
        setLeaderIfAbsent("注册部", "zhouba");
        setLeaderIfAbsent("软件开发部", "wujiu");
        setLeaderIfAbsent("生产部", "zhengshi");
    }

    /**
     * 幂等升级：为现有部门补全 leader_id（已存在数据库时执行）
     *
     * Department.leader_id 是新增字段，老数据库该列为 NULL。
     * 此方法按 name 查部门，按 username 查用户，幂等设置 leader。
     */
    private void upgradeDepartmentLeaders() {
        setLeaderIfAbsent("研发中心", "admin");
        setLeaderIfAbsent("结构设计部", "zhangsan");
        setLeaderIfAbsent("电路设计部", "lisi");
        setLeaderIfAbsent("测试验证部", "wangwu");
        setLeaderIfAbsent("体系管理部", "zhaoliu");
        setLeaderIfAbsent("质量部", "sunqi");
        setLeaderIfAbsent("注册部", "zhouba");
        setLeaderIfAbsent("软件开发部", "wujiu");
        setLeaderIfAbsent("生产部", "zhengshi");
    }

    /**
     * 幂等设置部门 leader：仅当部门当前 leader 为 null 时设置。
     * 调岗场景：admin 手工更新 leader 后此方法不会覆盖（参见开发计划 GAP #4）。
     */
    private void setLeaderIfAbsent(String deptName, String leaderUsername) {
        departmentRepository.findByName(deptName).ifPresent(dept -> {
            if (dept.getLeader() != null) {
                return;
            }
            userRepository.findByUsername(leaderUsername).ifPresent(leader -> {
                dept.setLeader(leader);
                departmentRepository.save(dept);
            });
        });
    }

    /**
     * 幂等初始化：文档分类
     *
     * 体系文档 5 大分类（docType=SYSTEM）
     * 研发资料 7 大分类（docType=RESEARCH）
     *
     * 幂等策略：按 code 检查，已存在则跳过（支持已有数据库平滑升级）
     */
    private void initializeDocumentCategories() {
        // 体系文档分类（SYSTEM）
        createCategoryIfAbsent("QUALITY_MANUAL", "质量手册", "公司质量方针、目标与体系范围", 1, DocumentType.SYSTEM);
        createCategoryIfAbsent("PROCEDURE", "程序文件", "体系要求的过程描述文件", 2, DocumentType.SYSTEM);
        createCategoryIfAbsent("WORK_INSTRUCTION", "作业指导书", "具体操作步骤说明", 3, DocumentType.SYSTEM);
        createCategoryIfAbsent("RECORD", "记录表单", "表格、记录与模板", 4, DocumentType.SYSTEM);
        createCategoryIfAbsent("EXTERNAL", "外部文件", "法规、标准、客户文件等", 5, DocumentType.SYSTEM);

        // 研发资料分类（RESEARCH）- 按技术领域分类
        createCategoryIfAbsent("DESIGN_PRINCIPLE", "设计原理图", "机械/电路设计原理图、方案图", 101, DocumentType.RESEARCH);
        createCategoryIfAbsent("PARAM_SPEC", "参数规格书", "技术参数、规格说明、BOM 表", 102, DocumentType.RESEARCH);
        createCategoryIfAbsent("ALGORITHM_DOC", "算法文档", "输注算法、控制逻辑、信号处理", 103, DocumentType.RESEARCH);
        createCategoryIfAbsent("TEST_DATA", "测试数据", "测试报告、验证数据、实验记录", 104, DocumentType.RESEARCH);
        createCategoryIfAbsent("SIMULATION_FILE", "仿真文件", "仿真模型、有限元分析、CFD 结果", 105, DocumentType.RESEARCH);
        createCategoryIfAbsent("PROTOTYPE_FILE", "原型文件", "原型设计、样件数据、3D 模型", 106, DocumentType.RESEARCH);
        createCategoryIfAbsent("TECH_RESEARCH", "技术调研报告", "技术调研、文献综述、竞品分析", 107, DocumentType.RESEARCH);

        // 原理文档分类（RESEARCH）- 按来源/保密维度分类（用户 2026-08-04 需求补充）
        // 用于存储测试/结构/电路原理文档，区分工厂工艺原理、第三方原理（公开或涉密）、常规不保密原理
        createCategoryIfAbsent("FACTORY_PROCESS", "工厂工艺原理", "工厂实际工艺原理文档（内部掌握）", 108, DocumentType.RESEARCH);
        createCategoryIfAbsent("THIRD_PARTY_PRINCIPLE", "第三方原理", "第三方机构原理文档（公开或涉密，需溯源）", 109, DocumentType.RESEARCH);
        createCategoryIfAbsent("COMMON_PRINCIPLE", "常规原理", "常规不保密的原理文档", 110, DocumentType.RESEARCH);
    }

    /**
     * 幂等初始化：供应商主数据（示例种子数据）
     *
     * 仅在 t_supplier 表为空时执行，避免重复创建。
     * 包含 3 家典型供应商：原材料、零部件、外协加工。
     */
    private void initializeSuppliers() {
        if (supplierRepository.count() > 0) {
            return;
        }

        createSupplier("SUP-001", "深圳市精密机械有限公司",
                "王经理", "13800100001", "wang@precision-mech.com",
                "原材料", QualificationStatus.QUALIFIED,
                "李质量", "13800100011");
        createSupplier("SUP-002", "上海微电子科技有限公司",
                "陈经理", "13800100002", "chen@micro-electro.com",
                "零部件", QualificationStatus.QUALIFIED,
                "张质量", "13800100012");
        createSupplier("SUP-003", "苏州外协加工厂",
                "刘经理", "13800100003", "liu@oem-factory.com",
                "外协加工", QualificationStatus.PENDING,
                "周质量", "13800100013");
    }

    private void createSupplier(String supplierCode, String name,
                                 String contact, String phone, String email,
                                 String category, QualificationStatus status,
                                 String qualityContactName, String qualityContactPhone) {
        Supplier s = new Supplier();
        s.setSupplierCode(supplierCode);
        s.setName(name);
        s.setContact(contact);
        s.setPhone(phone);
        s.setEmail(email);
        s.setCategory(category);
        s.setQualificationStatus(status);
        s.setQualityContactName(qualityContactName);
        s.setQualityContactPhone(qualityContactPhone);
        s.setEnabled(true);
        supplierRepository.save(s);
    }

    private DocumentCategory createCategoryIfAbsent(String code, String name, String description,
                                                     int sortOrder, DocumentType docType) {
        if (categoryRepository.existsByCode(code)) {
            return categoryRepository.findByCode(code).orElseThrow();
        }
        return categoryRepository.save(new DocumentCategory(code, name, description, sortOrder, docType));
    }

    private Role createRole(String name, String code, String description, String... permissions) {
        Role role = new Role(name, code, description);
        role.setPermissions(new HashSet<>(Arrays.asList(permissions)));
        return roleRepository.save(role);
    }

    private Department createDept(String name, String description) {
        return departmentRepository.save(new Department(name, description, null));
    }

    private User createUser(String username, String password, String realName, String employeeNo,
                            String email, String phone, Role role, Department department) {
        User user = new User();
        user.setUsername(username);
        user.setPassword(passwordEncoder.encode(password));
        user.setRealName(realName);
        user.setEmployeeNo(employeeNo);
        user.setEmail(email);
        user.setPhone(phone);
        user.setRole(role);
        user.setDepartment(department);
        user.setEnabled(true);
        return userRepository.save(user);
    }
}
