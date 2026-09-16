package com.insulinpump.usermgmt.service;

import com.insulinpump.usermgmt.audit.Auditable;
import com.insulinpump.usermgmt.config.RequestContextFilter;
import com.insulinpump.usermgmt.dto.DocumentDetailDto;
import com.insulinpump.usermgmt.dto.DocumentDiffDto;
import com.insulinpump.usermgmt.dto.DocumentListDto;
import com.insulinpump.usermgmt.dto.DocumentRevisionDto;
import com.insulinpump.usermgmt.dto.DocumentUpdateRequest;
import com.insulinpump.usermgmt.dto.ResearchMaterialDetailDto;
import com.insulinpump.usermgmt.dto.ResearchMaterialListDto;
import com.insulinpump.usermgmt.dto.ReviewRecordDto;
import com.insulinpump.usermgmt.dto.ShareDto;
import com.insulinpump.usermgmt.exception.ChecksumMismatchException;
import com.insulinpump.usermgmt.model.*;
import com.insulinpump.usermgmt.repository.DocumentCategoryRepository;
import com.insulinpump.usermgmt.repository.DocumentFileRepository;
import com.insulinpump.usermgmt.repository.DocumentRepository;
import com.insulinpump.usermgmt.repository.DocumentReviewRepository;
import com.insulinpump.usermgmt.repository.DocumentRevisionRepository;
import com.insulinpump.usermgmt.repository.DocumentShareRepository;
import com.insulinpump.usermgmt.repository.UserRepository;
import com.insulinpump.usermgmt.util.ChecksumUtil;
import jakarta.persistence.criteria.JoinType;
import jakarta.persistence.criteria.Predicate;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.data.jpa.domain.Specification;
import org.springframework.orm.ObjectOptimisticLockingFailureException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.Optional;
import java.util.Set;

/**
 * 文档 Service
 *
 * 核心职责：
 *  - 文档 CRUD（含 BLOB 分表存储）
 *  - 文件类型/大小校验（白名单）
 *  - 可见性权限校验（PUBLIC / DEPARTMENT / ASSIGNEES）
 *  - SHA-256 checksum 计算
 *  - @Transactional 保证元数据与 BLOB 原子性
 *
 * 可见性规则（双模型并存）：
 *  - SYSTEM 文档：沿用 DocumentVisibility（PUBLIC/DEPARTMENT/ASSIGNEES），不在本次改造范围
 *  - RESEARCH 资料：使用统一可见性规则（DataVisibilityChecker） + SHARED 策略（DocumentShare 表）
 *    - ADMIN       : 全见
 *    - owner       : 自己录入的全见（含 TOP_SECRET）
 *    - 同部门员工  : 本部门他人数据全见（含 TOP_SECRET，所有员工，不限于部门负责人）
 *    - 跨部门授权  : allowedLevels 命中保密等级可见（含 TOP_SECRET，由 ADMIN 显式授权）
 *    - 普通员工    : 自己录入的 + 本部门他人 + allowedLevels 内的他人数据 + 被分享给自己的（默认空集 = 自己 + 本部门）
 *    - TOP_SECRET  : 不可通过 DocumentShare 分享，但同部门员工与 allowedLevels 授权用户仍可见
 */
@Service
public class DocumentService {

    private final DocumentRepository documentRepository;
    private final DocumentFileRepository fileRepository;
    private final DocumentCategoryRepository categoryRepository;
    private final DocumentRevisionRepository revisionRepository;
    private final DocumentReviewRepository reviewRepository;
    private final DocumentShareRepository shareRepository;
    private final UserRepository userRepository;
    private final DataVisibilityChecker dataVisibilityChecker;
    private final SignatureService signatureService;
    private final NotificationService notificationService;

    /** 单文件大小上限：50 MB */
    private static final long MAX_FILE_SIZE = 50L * 1024 * 1024;

    /** 体系文档允许的文件扩展名白名单 */
    private static final Set<String> SYSTEM_ALLOWED_EXTENSIONS = Set.of(
            "pdf", "jpg", "jpeg", "png", "gif",
            "doc", "docx", "xls", "xlsx"
    );

    /** 体系文档允许的 MIME 类型白名单 */
    private static final Set<String> SYSTEM_ALLOWED_MIME_TYPES = Set.of(
            "application/pdf",
            "image/jpeg", "image/png", "image/gif",
            "application/msword",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/vnd.ms-excel",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    );

    /** 研发资料允许的文件扩展名白名单（比体系文档更宽松，支持 ppt/txt/csv/md/zip 等） */
    private static final Set<String> RESEARCH_ALLOWED_EXTENSIONS = Set.of(
            "pdf", "jpg", "jpeg", "png", "gif",
            "doc", "docx", "xls", "xlsx", "ppt", "pptx",
            "txt", "csv", "md",
            "zip", "rar", "7z"
    );

    /** 研发资料允许的 MIME 类型白名单 */
    private static final Set<String> RESEARCH_ALLOWED_MIME_TYPES = Set.of(
            "application/pdf",
            "image/jpeg", "image/png", "image/gif",
            "application/msword",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/vnd.ms-excel",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "application/vnd.ms-powerpoint",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            "text/plain", "text/csv", "text/markdown",
            "application/zip", "application/x-zip-compressed",
            "application/x-rar-compressed", "application/x-7z-compressed",
            "application/octet-stream"
    );

    public DocumentService(DocumentRepository documentRepository,
                           DocumentFileRepository fileRepository,
                           DocumentCategoryRepository categoryRepository,
                           DocumentRevisionRepository revisionRepository,
                           DocumentReviewRepository reviewRepository,
                           DocumentShareRepository shareRepository,
                           UserRepository userRepository,
                           DataVisibilityChecker dataVisibilityChecker,
                           SignatureService signatureService,
                           NotificationService notificationService) {
        this.documentRepository = documentRepository;
        this.fileRepository = fileRepository;
        this.categoryRepository = categoryRepository;
        this.revisionRepository = revisionRepository;
        this.reviewRepository = reviewRepository;
        this.shareRepository = shareRepository;
        this.userRepository = userRepository;
        this.dataVisibilityChecker = dataVisibilityChecker;
        this.signatureService = signatureService;
        this.notificationService = notificationService;
    }

    // ============ 列表查询 ============

    public Page<DocumentListDto> listDocuments(int page, int size, Long categoryId,
                                                String keyword, User currentUser) {
        PageRequest pr = PageRequest.of(page, size, Sort.by(Sort.Direction.DESC, "createdAt"));
        String kw = (keyword != null && !keyword.isBlank()) ? keyword.trim() : null;
        boolean admin = dataVisibilityChecker.isAdmin(currentUser);
        Long deptId = (!admin && currentUser.getDepartment() != null)
                ? currentUser.getDepartment().getId() : null;
        Long userId = !admin ? currentUser.getId() : null;

        Specification<Document> spec = (root, query, cb) -> {
            // count 查询不加 fetch，避免 count(*) 关联全表
            if (query.getResultType() != Long.class && query.getResultType() != long.class) {
                root.fetch("category", JoinType.LEFT);
                root.fetch("uploader", JoinType.LEFT).fetch("department", JoinType.LEFT);
                query.distinct(true);
            }

            List<Predicate> predicates = new ArrayList<>();

            if (categoryId != null) {
                predicates.add(cb.equal(root.get("category").get("id"), categoryId));
            }

            if (kw != null) {
                // cb.lower + 字面量 pattern，避免 Hibernate 参数绑定推断为 bytea
                predicates.add(cb.like(cb.lower(root.get("title")), "%" + kw.toLowerCase() + "%"));
            }

            if (!admin) {
                Predicate pub = cb.equal(root.get("visibility"), DocumentVisibility.PUBLIC);
                Predicate dept = (deptId != null)
                        ? cb.and(cb.equal(root.get("visibility"), DocumentVisibility.DEPARTMENT),
                                 cb.equal(root.get("department").get("id"), deptId))
                        : cb.disjunction();
                Predicate own = cb.and(cb.equal(root.get("visibility"), DocumentVisibility.ASSIGNEES),
                                       cb.equal(root.get("uploader").get("id"), userId));
                predicates.add(cb.or(pub, dept, own));
            }

            return cb.and(predicates.toArray(new Predicate[0]));
        };

        Page<Document> docs = documentRepository.findAll(spec, pr);
        return docs.map(this::toListDto);
    }

    // ============ 详情查询 ============

    public DocumentDetailDto getDocumentDetail(Long id, User currentUser) {
        Document doc = documentRepository.findById(id)
                .orElseThrow(() -> new IllegalArgumentException("文档不存在"));
        checkVisibility(doc, currentUser);
        return toDetailDto(doc);
    }

    // ============ 上传 ============

    @Transactional
    @Auditable(action = "UPLOAD_DOCUMENT", entityType = "DOCUMENT")
    public DocumentDetailDto upload(MultipartFile file, String title, Long categoryId,
                                     String description, DocumentVisibility visibility,
                                     User uploader) {
        // 1. 校验文件
        validateFile(file);

        // 2. 校验分类
        DocumentCategory category = categoryRepository.findById(categoryId)
                .orElseThrow(() -> new IllegalArgumentException("分类不存在"));

        // 3. 提取文件信息
        String originalName = file.getOriginalFilename();
        String extension = extractExtension(originalName);
        String mimeType = file.getContentType();
        long size = file.getSize();

        // 4. 读取文件内容并计算 checksum
        byte[] content;
        try {
            content = file.getBytes();
        } catch (IOException e) {
            throw new IllegalStateException("读取文件失败: " + e.getMessage(), e);
        }
        String checksum = ChecksumUtil.sha256(content);

        // 5. 保存文档元数据
        Document doc = new Document();
        doc.setTitle(title);
        doc.setDescription(description);
        doc.setFileName(originalName);
        doc.setFileSize(size);
        doc.setFileType(mimeType);
        doc.setFileExtension(extension);
        doc.setVisibility(visibility);
        doc.setCategory(category);
        doc.setUploader(uploader);
        // DEPARTMENT 可见性时，记录上传人所在部门
        if (visibility == DocumentVisibility.DEPARTMENT) {
            doc.setDepartment(uploader.getDepartment());
        }
        documentRepository.save(doc);

        // 6. 保存 BLOB
        DocumentFile docFile = new DocumentFile(doc.getId(), content, checksum);
        fileRepository.save(docFile);

        // 7. 返回详情（重新查询以获得完整关联）
        Document saved = documentRepository.findById(doc.getId()).orElseThrow();
        return toDetailDto(saved);
    }

    // ============ 更新元数据 ============

    @Transactional
    @Auditable(action = "UPDATE_DOCUMENT", entityType = "DOCUMENT")
    public DocumentDetailDto update(Long id, DocumentUpdateRequest req, User currentUser) {
        Document doc = documentRepository.findById(id)
                .orElseThrow(() -> new IllegalArgumentException("文档不存在"));

        // 仅 ADMIN 或上传人可修改
        if (!dataVisibilityChecker.isAdmin(currentUser) && !doc.getUploader().getId().equals(currentUser.getId())) {
            throw new SecurityException("无权修改该文档");
        }

        if (req.getTitle() != null && !req.getTitle().isBlank()) {
            doc.setTitle(req.getTitle());
        }
        if (req.getDescription() != null) {
            doc.setDescription(req.getDescription());
        }
        if (req.getCategoryId() != null) {
            DocumentCategory category = categoryRepository.findById(req.getCategoryId())
                    .orElseThrow(() -> new IllegalArgumentException("分类不存在"));
            doc.setCategory(category);
        }
        if (req.getVisibility() != null) {
            DocumentVisibility v = DocumentVisibility.valueOf(req.getVisibility());
            doc.setVisibility(v);
            if (v == DocumentVisibility.DEPARTMENT) {
                doc.setDepartment(currentUser.getDepartment());
            } else {
                doc.setDepartment(null);
            }
        }

        Document saved = documentRepository.save(doc);
        return toDetailDto(saved);
    }

    // ============ 删除 ============

    @Transactional
    @Auditable(action = "DELETE_DOCUMENT", entityType = "DOCUMENT")
    public void delete(Long id, User currentUser) {
        Document doc = documentRepository.findById(id)
                .orElseThrow(() -> new IllegalArgumentException("文档不存在"));
        // 仅 ADMIN 可删除（@PreAuthorize 已在 Controller 层强制，此处双重校验）
        if (!dataVisibilityChecker.isAdmin(currentUser)) {
            throw new SecurityException("无权删除文档");
        }
        // 先删分享关系（RESEARCH 类型才有），再删 BLOB，最后删元数据
        shareRepository.deleteByDocumentId(id);
        fileRepository.deleteByDocumentId(id);
        documentRepository.deleteById(id);
    }

    // ============ 下载/预览 ============

    /**
     * 获取文件内容（下载/预览共用）
     * 包含可见性校验 + BLOB 存在性校验 + checksum 完整性校验（ALCOA+）
     *
     * 必须在事务上下文中执行：DocumentFile.content 字段使用 @Lob 注解，
     * 在 PostgreSQL + Hibernate 下映射为 oid 类型（Large Object API），
     * 读取 OID 类型 LOB 必须在事务中，否则抛出 "unable to access lob stream"。
     *
     * checksum 校验：从存储读取后重新计算 SHA-256，与 t_document_file.checksum 比对。
     * 不一致抛 ChecksumMismatchException（410 Gone），表示数据已损坏或被篡改。
     */
    @Transactional(readOnly = true)
    public DocumentFile getFileContent(Long id, User currentUser) {
        Document doc = documentRepository.findById(id)
                .orElseThrow(() -> new IllegalArgumentException("文档不存在"));
        checkVisibility(doc, currentUser);
        // BLOB 存在性校验（修复 critical gap: BLOB 已删除但元数据存在）
        DocumentFile docFile = fileRepository.findByDocumentId(id)
                .orElseThrow(() -> new IllegalStateException("文件内容不存在，请联系管理员"));
        // checksum 完整性校验（ALCOA+ 数据完整性）
        if (docFile.getChecksum() == null
                || !ChecksumUtil.verify(docFile.getContent(), docFile.getChecksum())) {
            throw new ChecksumMismatchException(
                    "文件 checksum 校验失败，文件可能已损坏或被篡改", id, "DOCUMENT");
        }
        return docFile;
    }

    /**
     * 获取文档元数据原始实体（无可见性校验，仅供已通过校验的内部流程使用）
     * 用于下载/预览时获取文件名与 MIME 类型
     */
    public Document getDocumentRaw(Long id) {
        return documentRepository.findById(id)
                .orElseThrow(() -> new IllegalArgumentException("文档不存在"));
    }

    // ============ 版本控制 ============

    /**
     * 发布文档（首次发布或发布新版本）— 直接发布通道
     *
     * 状态转换:
     *  - DRAFT -> PUBLISHED (首次发布, v1.0)
     *  - PUBLISHED -> PUBLISHED (新版本, v1.x+1, 旧状态快照到 Revision)
     *  - OBSOLETE/REVIEW -> 拒绝
     *
     * 适用场景: ADMIN 或上传人直接发布（跳过审批流）。
     * 走审批流请用 submitForReview -> approve。
     *
     * 事务保证: Revision 快照保存 + Document 更新 + 电子签名 原子性。
     * 并发安全: @Version 乐观锁防止并发发布冲突。
     * 合规: 调用 SignatureService.verifyAndRecord 完成 FDA Part 11 电子签名。
     */
    @Transactional
    @Auditable(action = "PUBLISH", entityType = "DOCUMENT")
    public DocumentDetailDto publish(Long id, String changeLog, User user,
                                     String password, String meaning) {
        try {
            Document doc = documentRepository.findById(id)
                    .orElseThrow(() -> new IllegalArgumentException("文档不存在"));

            // 权限: ADMIN 或上传人可发布
            if (!dataVisibilityChecker.isAdmin(user) && !doc.getUploader().getId().equals(user.getId())) {
                throw new SecurityException("无权发布该文档");
            }

            // 状态校验: REVIEW 状态必须走 approve 流程，不允许直接 publish
            DocumentStatus status = doc.getStatus();
            if (status == DocumentStatus.OBSOLETE) {
                throw new IllegalStateException("已作废的文档不能发布");
            }
            if (status == DocumentStatus.REVIEW) {
                throw new IllegalStateException("审核中的文档请走审批流程（approve）");
            }
            if (status != DocumentStatus.DRAFT && status != DocumentStatus.PUBLISHED) {
                throw new IllegalStateException("当前状态不允许发布: " + status);
            }

            // 记录审计 before 快照（发布前的状态）
            RequestContextFilter.setAuditBefore(
                    "version=" + doc.getVersion() + ", status=" + doc.getStatus());

            Document saved = doPublish(doc, user, changeLog);

            // 电子签名（与业务在同一事务，业务失败则签名一起回滚）
            signatureService.verifyAndRecord(user, password, "PUBLISH", "DOCUMENT", id, meaning);

            return toDetailDto(saved);
        } catch (ObjectOptimisticLockingFailureException e) {
            throw new IllegalStateException("文档正被其他人编辑，请刷新后重试", e);
        }
    }

    /**
     * 内部发布逻辑（已通过权限和状态校验）
     *
     * 步骤:
     *  1. 判断首次/增量发布
     *  2. 创建 Revision 快照（保存当前状态）
     *  3. 标记上一条 Revision 为已作废
     *  4. 更新 Document: version 递增、status=PUBLISHED、effectiveDate=now
     *
     * @return 保存后的 Document（含新版本号）
     */
    private Document doPublish(Document doc, User user, String changeLog) {
        boolean isFirstPublish = (doc.getVersion() == null);

        // 获取当前 BLOB
        DocumentFile docFile = fileRepository.findByDocumentId(doc.getId())
                .orElseThrow(() -> new IllegalStateException("文件内容不存在，无法发布"));

        // 计算新版本号
        String oldVersion = isFirstPublish ? null : doc.getVersion();
        String newVersion = isFirstPublish ? "v1.0" : calculateNextVersion(doc.getVersion());

        // 获取上一条 Revision（版本链）
        Long supersedesRevId = null;
        if (!isFirstPublish) {
            Optional<DocumentRevision> lastRev = revisionRepository
                    .findTopByDocumentIdOrderByPublishedAtDesc(doc.getId());
            if (lastRev.isPresent()) {
                supersedesRevId = lastRev.get().getId();
            }
        }

        // 创建 Revision 快照（记录当前状态）
        DocumentRevision revision = new DocumentRevision(
                doc.getId(),
                isFirstPublish ? "v1.0" : oldVersion,  // 快照版本号 = 旧版本号
                doc.getTitle(),
                doc.getDescription(),
                doc.getFileName(),
                doc.getFileSize(),
                doc.getFileType(),
                doc.getFileExtension(),
                docFile.getContent(),          // BLOB 副本
                docFile.getChecksum(),
                user.getId(),
                isFirstPublish ? LocalDateTime.now() : doc.getEffectiveDate(),
                changeLog,
                supersedesRevId
        );
        revisionRepository.save(revision);

        // 如果非首次发布，标记上一条 Revision 为已作废
        if (!isFirstPublish && supersedesRevId != null) {
            revisionRepository.findById(supersedesRevId).ifPresent(prevRev -> {
                prevRev.setObsoleteDate(LocalDateTime.now());
                revisionRepository.save(prevRev);
            });
        }

        // 更新 Document 为新版本
        doc.setVersion(newVersion);
        doc.setStatus(DocumentStatus.PUBLISHED);
        doc.setEffectiveDate(LocalDateTime.now());

        return documentRepository.save(doc);
    }

    // ============ 审批工作流 ============

    /**
     * 提交评审 — DRAFT -> REVIEW
     *
     * 权限: ADMIN 或上传人
     * 不创建 Review 记录（仅状态转换，等待 ADMIN 审批）
     */
    @Transactional
    @Auditable(action = "SUBMIT_REVIEW", entityType = "DOCUMENT")
    public DocumentDetailDto submitForReview(Long id, User user) {
        Document doc = documentRepository.findById(id)
                .orElseThrow(() -> new IllegalArgumentException("文档不存在"));

        // 权限: ADMIN 或上传人
        if (!dataVisibilityChecker.isAdmin(user) && !doc.getUploader().getId().equals(user.getId())) {
            throw new SecurityException("无权提交该文档评审");
        }

        // 状态校验
        if (doc.getStatus() != DocumentStatus.DRAFT) {
            throw new IllegalStateException("仅草稿状态可提交评审，当前: " + doc.getStatus());
        }

        doc.setStatus(DocumentStatus.REVIEW);
        Document saved = documentRepository.save(doc);

        // 通知所有管理员：生成待办审批（APPROVAL_TASK）
        String uploaderName = doc.getUploader() != null ? doc.getUploader().getRealName() : "未知用户";
        notificationService.notifyAdmins(
                NotificationType.APPROVAL_TASK,
                "待办审批",
                "员工 " + uploaderName + " 提交文档《" + doc.getTitle() + "》待您审批",
                "DOCUMENT", id, "/documents");

        return toDetailDto(saved);
    }

    /**
     * 审批通过 — REVIEW -> PUBLISHED
     *
     * 权限: 仅 ADMIN
     * 复用 doPublish 内部逻辑（创建 Revision 快照、版本号递增）
     * 创建 DocumentReview(APPROVED) 记录，versionAfter=新版本号
     * 合规: 调用 SignatureService.verifyAndRecord 完成 FDA Part 11 电子签名。
     */
    @Transactional
    @Auditable(action = "APPROVE", entityType = "DOCUMENT")
    public DocumentDetailDto approve(Long id, String comment, User user,
                                     String password, String meaning) {
        try {
            if (!dataVisibilityChecker.isAdmin(user)) {
                throw new SecurityException("仅管理员可审批文档");
            }

            Document doc = documentRepository.findById(id)
                    .orElseThrow(() -> new IllegalArgumentException("文档不存在"));

            if (doc.getStatus() != DocumentStatus.REVIEW) {
                throw new IllegalStateException("仅审核中状态可审批，当前: " + doc.getStatus());
            }

            // 记录审计 before 快照
            RequestContextFilter.setAuditBefore(
                    "version=" + doc.getVersion() + ", status=" + doc.getStatus());

            // 执行发布（创建 Revision、版本号递增、status=PUBLISHED）
            Document saved = doPublish(doc, user, "审批通过" + (comment != null && !comment.isBlank() ? "：" + comment : ""));

            // 创建审批记录
            DocumentReview review = new DocumentReview(
                    id, user.getId(), ReviewDecision.APPROVED, comment, saved.getVersion());
            reviewRepository.save(review);

            // 电子签名（与业务在同一事务）
            signatureService.verifyAndRecord(user, password, "APPROVE", "DOCUMENT", id, meaning);

            // 关闭该文档的所有"待办审批"待办，并通知上传人审批结果
            notificationService.markTaskDoneByRelated(
                    NotificationType.APPROVAL_TASK, "DOCUMENT", id);
            User uploader = doc.getUploader();
            if (uploader != null && !uploader.getId().equals(user.getId())) {
                notificationService.create(
                        uploader.getId(),
                        NotificationType.APPROVAL_RESULT,
                        "审批结果",
                        "您提交的文档《" + doc.getTitle() + "》已审批通过，版本更新为 "
                                + saved.getVersion(),
                        "DOCUMENT", id, "/documents");
            }

            // 审批通过 = 正式发布，向全体用户广播发布公告（SYSTEM_ANNOUNCEMENT）
            notificationService.broadcast(
                    NotificationType.SYSTEM_ANNOUNCEMENT,
                    "新文档发布",
                    "文档《" + doc.getTitle() + "》已审批通过并正式发布，版本更新为 "
                            + saved.getVersion(),
                    "DOCUMENT", id, "/documents");

            return toDetailDto(saved);
        } catch (ObjectOptimisticLockingFailureException e) {
            throw new IllegalStateException("文档正被其他人编辑，请刷新后重试", e);
        }
    }

    /**
     * 审批驳回 — REVIEW -> DRAFT
     *
     * 权限: 仅 ADMIN
     * comment 必填（驳回必须给理由）
     * 创建 DocumentReview(REJECTED) 记录，versionAfter=null
     * 不创建 Revision（被驳回，不发布）
     * 合规: 调用 SignatureService.verifyAndRecord 完成 FDA Part 11 电子签名。
     */
    @Transactional
    @Auditable(action = "REJECT", entityType = "DOCUMENT")
    public DocumentDetailDto reject(Long id, String comment, User user,
                                    String password, String meaning) {
        if (!dataVisibilityChecker.isAdmin(user)) {
            throw new SecurityException("仅管理员可审批文档");
        }
        if (comment == null || comment.isBlank()) {
            throw new IllegalArgumentException("驳回必须填写审批意见");
        }

        Document doc = documentRepository.findById(id)
                .orElseThrow(() -> new IllegalArgumentException("文档不存在"));

        if (doc.getStatus() != DocumentStatus.REVIEW) {
            throw new IllegalStateException("仅审核中状态可驳回，当前: " + doc.getStatus());
        }

        // 记录审计 before 快照
        RequestContextFilter.setAuditBefore(
                "version=" + doc.getVersion() + ", status=" + doc.getStatus());

        doc.setStatus(DocumentStatus.DRAFT);
        Document saved = documentRepository.save(doc);

        // 创建审批记录
        DocumentReview review = new DocumentReview(
                id, user.getId(), ReviewDecision.REJECTED, comment, null);
        reviewRepository.save(review);

        // 电子签名（与业务在同一事务）
        signatureService.verifyAndRecord(user, password, "REJECT", "DOCUMENT", id, meaning);

        // 关闭该文档的所有"待办审批"待办，并通知上传人审批结果
        notificationService.markTaskDoneByRelated(NotificationType.APPROVAL_TASK, "DOCUMENT", id);
        User uploader = doc.getUploader();
        if (uploader != null && !uploader.getId().equals(user.getId())) {
            notificationService.create(
                    uploader.getId(),
                    NotificationType.APPROVAL_RESULT,
                    "审批结果",
                    "您提交的文档《" + doc.getTitle() + "》被驳回，意见：" + comment,
                    "DOCUMENT", id, "/documents");
        }

        return toDetailDto(saved);
    }

    /**
     * 作废 — PUBLISHED -> OBSOLETE
     *
     * 权限: 仅 ADMIN
     * 设置 obsoleteDate，文档不可再 publish/approve
     * 合规: 调用 SignatureService.verifyAndRecord 完成 FDA Part 11 电子签名。
     */
    @Transactional
    @Auditable(action = "RETIRE", entityType = "DOCUMENT")
    public DocumentDetailDto retire(Long id, User user, String password, String meaning) {
        if (!dataVisibilityChecker.isAdmin(user)) {
            throw new SecurityException("仅管理员可作废文档");
        }

        Document doc = documentRepository.findById(id)
                .orElseThrow(() -> new IllegalArgumentException("文档不存在"));

        if (doc.getStatus() != DocumentStatus.PUBLISHED) {
            throw new IllegalStateException("仅已发布状态可作废，当前: " + doc.getStatus());
        }

        // 记录审计 before 快照
        RequestContextFilter.setAuditBefore(
                "version=" + doc.getVersion() + ", status=" + doc.getStatus());

        doc.setStatus(DocumentStatus.OBSOLETE);
        doc.setObsoleteDate(LocalDateTime.now());
        Document saved = documentRepository.save(doc);

        // 电子签名（与业务在同一事务）
        signatureService.verifyAndRecord(user, password, "RETIRE", "DOCUMENT", id, meaning);

        return toDetailDto(saved);
    }

    /**
     * 列出文档的审批历史（按时间倒序）
     */
    @Transactional(readOnly = true)
    public List<ReviewRecordDto> listReviews(Long documentId, User user) {
        Document doc = documentRepository.findById(documentId)
                .orElseThrow(() -> new IllegalArgumentException("文档不存在"));
        checkVisibility(doc, user);
        List<DocumentReview> reviews = reviewRepository.findByDocumentIdOrderByReviewedAtDesc(documentId);
        List<ReviewRecordDto> dtos = new ArrayList<>();
        for (DocumentReview r : reviews) {
            User reviewer = userRepository.findById(r.getReviewerId()).orElse(null);
            String reviewerName = reviewer != null ? reviewer.getRealName() : null;
            dtos.add(new ReviewRecordDto(
                    r.getId(), r.getDocumentId(), r.getReviewerId(), reviewerName,
                    r.getDecision(), r.getComment(), r.getReviewedAt(), r.getVersionAfter()));
        }
        return dtos;
    }


    /**
     * 列出文档的修订历史（按发布时间倒序，不含 BLOB）
     */
    @Transactional(readOnly = true)
    public List<DocumentRevisionDto> listRevisions(Long documentId, User user) {
        Document doc = documentRepository.findById(documentId)
                .orElseThrow(() -> new IllegalArgumentException("文档不存在"));
        checkVisibility(doc, user);

        List<DocumentRevision> revisions = revisionRepository
                .findByDocumentIdOrderByPublishedAtDesc(documentId);

        List<DocumentRevisionDto> dtos = new ArrayList<>();
        for (DocumentRevision rev : revisions) {
            DocumentRevisionDto dto = new DocumentRevisionDto();
            dto.setId(rev.getId());
            dto.setDocumentId(rev.getDocumentId());
            dto.setVersion(rev.getVersion());
            dto.setTitle(rev.getTitle());
            dto.setFileName(rev.getFileName());
            dto.setFileSize(rev.getFileSize());
            dto.setChangeLog(rev.getChangeLog());
            dto.setPublishedById(rev.getPublishedById());
            dto.setPublishedAt(rev.getPublishedAt());
            dto.setEffectiveDate(rev.getEffectiveDate());
            dto.setObsoleteDate(rev.getObsoleteDate());
            dto.setSupersedesRevId(rev.getSupersedesRevId());
            dtos.add(dto);
        }
        return dtos;
    }

    /**
     * 获取指定修订版本（含 BLOB contentSnapshot，用于下载历史版本）
     * 包含可见性校验 + checksum 完整性校验（ALCOA+）。
     */
    @Transactional(readOnly = true)
    public DocumentRevision getRevision(Long documentId, Long revId, User user) {
        Document doc = documentRepository.findById(documentId)
                .orElseThrow(() -> new IllegalArgumentException("文档不存在"));
        checkVisibility(doc, user);

        DocumentRevision rev = revisionRepository.findById(revId)
                .orElseThrow(() -> new IllegalArgumentException("修订版本不存在"));

        if (!rev.getDocumentId().equals(documentId)) {
            throw new IllegalArgumentException("修订版本不属于该文档");
        }

        // checksum 完整性校验（ALCOA+ 数据完整性，历史版本同样校验）
        if (rev.getChecksum() == null
                || !ChecksumUtil.verify(rev.getContentSnapshot(), rev.getChecksum())) {
            throw new ChecksumMismatchException(
                    "历史版本 checksum 校验失败，文件可能已损坏或被篡改",
                    documentId, "DOCUMENT");
        }
        return rev;
    }

    /**
     * 版本对比（元数据级 diff）
     *
     * 对比两个修订版本的元数据字段，checksum 不同时标记 contentChanged=true。
     */
    @Transactional(readOnly = true)
    public DocumentDiffDto diff(Long documentId, Long fromRevId, Long toRevId, User user) {
        Document doc = documentRepository.findById(documentId)
                .orElseThrow(() -> new IllegalArgumentException("文档不存在"));
        checkVisibility(doc, user);

        DocumentRevision fromRev = revisionRepository.findById(fromRevId)
                .orElseThrow(() -> new IllegalArgumentException("源修订版本不存在"));
        DocumentRevision toRev = revisionRepository.findById(toRevId)
                .orElseThrow(() -> new IllegalArgumentException("目标修订版本不存在"));

        if (!fromRev.getDocumentId().equals(documentId)) {
            throw new IllegalArgumentException("源修订版本不属于该文档");
        }
        if (!toRev.getDocumentId().equals(documentId)) {
            throw new IllegalArgumentException("目标修订版本不属于该文档");
        }

        List<DocumentDiffDto.FieldChange> changes = new ArrayList<>();
        addChangeIfDifferent(changes, "title", fromRev.getTitle(), toRev.getTitle());
        addChangeIfDifferent(changes, "description", fromRev.getDescription(), toRev.getDescription());
        addChangeIfDifferent(changes, "fileName", fromRev.getFileName(), toRev.getFileName());
        addChangeIfDifferent(changes, "fileSize", fromRev.getFileSize(), toRev.getFileSize());
        addChangeIfDifferent(changes, "fileType", fromRev.getFileType(), toRev.getFileType());
        addChangeIfDifferent(changes, "fileExtension", fromRev.getFileExtension(), toRev.getFileExtension());

        boolean contentChanged = !Objects.equals(fromRev.getChecksum(), toRev.getChecksum());
        if (contentChanged) {
            addChangeIfDifferent(changes, "checksum", fromRev.getChecksum(), toRev.getChecksum());
        }

        return new DocumentDiffDto(fromRev.getVersion(), toRev.getVersion(), changes, contentChanged);
    }

    /**
     * 回滚到指定版本（非破坏性）
     *
     * 创建新 PUBLISHED 版本，内容复制自目标 Revision。旧版本保留在历史中。
     * 仅 ADMIN 可执行回滚。
     * 合规: 调用 SignatureService.verifyAndRecord 完成 FDA Part 11 电子签名。
     */
    @Transactional
    @Auditable(action = "ROLLBACK", entityType = "DOCUMENT")
    public DocumentDetailDto rollback(Long documentId, Long revId, User user,
                                      String password, String meaning) {
        try {
            if (!dataVisibilityChecker.isAdmin(user)) {
                throw new SecurityException("仅管理员可执行回滚");
            }

            Document doc = documentRepository.findById(documentId)
                    .orElseThrow(() -> new IllegalArgumentException("文档不存在"));

            DocumentRevision targetRev = revisionRepository.findById(revId)
                    .orElseThrow(() -> new IllegalArgumentException("目标修订版本不存在"));

            if (!targetRev.getDocumentId().equals(documentId)) {
                throw new IllegalArgumentException("修订版本不属于该文档");
            }

            // 不能回滚到当前版本（无意义）
            if (doc.getVersion() != null && doc.getVersion().equals(targetRev.getVersion())) {
                throw new IllegalStateException("目标版本即当前版本，无需回滚");
            }

            // 记录审计 before 快照
            RequestContextFilter.setAuditBefore(
                    "version=" + doc.getVersion() + ", status=" + doc.getStatus()
                            + ", rollbackTo=" + targetRev.getVersion());

            // 1. 先快照当前状态到新 Revision（记录回滚前的状态）
            DocumentFile currentFile = fileRepository.findByDocumentId(documentId)
                    .orElseThrow(() -> new IllegalStateException("当前文件内容不存在"));

            Long currentSupersedesRevId = revisionRepository
                    .findTopByDocumentIdOrderByPublishedAtDesc(documentId)
                    .map(DocumentRevision::getId)
                    .orElse(null);

            String currentVersion = doc.getVersion() != null ? doc.getVersion() : "v1.0";
            DocumentRevision currentSnapshot = new DocumentRevision(
                    documentId,
                    currentVersion,
                    doc.getTitle(),
                    doc.getDescription(),
                    doc.getFileName(),
                    doc.getFileSize(),
                    doc.getFileType(),
                    doc.getFileExtension(),
                    currentFile.getContent(),
                    currentFile.getChecksum(),
                    user.getId(),
                    doc.getEffectiveDate(),
                    "回滚前快照（回滚至 " + targetRev.getVersion() + "）",
                    currentSupersedesRevId
            );
            revisionRepository.save(currentSnapshot);

            // 标记上一条为已作废
            if (currentSupersedesRevId != null) {
                revisionRepository.findById(currentSupersedesRevId).ifPresent(prevRev -> {
                    prevRev.setObsoleteDate(LocalDateTime.now());
                    revisionRepository.save(prevRev);
                });
            }

            // 2. 从目标 Revision 复制回 Document + DocumentFile
            doc.setTitle(targetRev.getTitle());
            doc.setDescription(targetRev.getDescription());
            doc.setFileName(targetRev.getFileName());
            doc.setFileSize(targetRev.getFileSize());
            doc.setFileType(targetRev.getFileType());
            doc.setFileExtension(targetRev.getFileExtension());

            currentFile.setContent(targetRev.getContentSnapshot());
            currentFile.setChecksum(targetRev.getChecksum());
            fileRepository.save(currentFile);

            // 3. 版本号递增，状态 PUBLISHED
            String newVersion = calculateNextVersion(currentVersion);
            doc.setVersion(newVersion);
            doc.setStatus(DocumentStatus.PUBLISHED);
            doc.setEffectiveDate(LocalDateTime.now());

            Document saved = documentRepository.save(doc);

            // 电子签名（与业务在同一事务）
            signatureService.verifyAndRecord(user, password, "ROLLBACK", "DOCUMENT", documentId, meaning);

            return toDetailDto(saved);
        } catch (ObjectOptimisticLockingFailureException e) {
            throw new IllegalStateException("文档正被其他人编辑，请刷新后重试", e);
        }
    }

    // ============ 版本控制辅助方法 ============

    /**
     * 计算下一版本号（minor 递增）
     * v1.0 -> v1.1, v1.1 -> v1.2, v2.3 -> v2.4
     */
    private String calculateNextVersion(String currentVersion) {
        if (currentVersion == null || !currentVersion.startsWith("v")) {
            return "v1.0";
        }
        try {
            String nums = currentVersion.substring(1);  // 去掉 "v"
            String[] parts = nums.split("\\.");
            int major = Integer.parseInt(parts[0]);
            int minor = parts.length > 1 ? Integer.parseInt(parts[1]) : 0;
            return "v" + major + "." + (minor + 1);
        } catch (NumberFormatException e) {
            return "v1.0";
        }
    }

    /**
     * 辅助: 如果两个值不同，添加一个 FieldChange 到列表
     */
    private void addChangeIfDifferent(List<DocumentDiffDto.FieldChange> changes,
                                       String field, Object oldVal, Object newVal) {
        if (!Objects.equals(oldVal, newVal)) {
            changes.add(new DocumentDiffDto.FieldChange(field, oldVal, newVal));
        }
    }

    // ============ 可见性校验 ============

    private void checkVisibility(Document doc, User user) {
        // ADMIN 绕过
        if (dataVisibilityChecker.isAdmin(user)) {
            return;
        }
        // RESEARCH 类型：统一可见性规则（owner + 同部门 + allowedLevels + category grant）+ SHARED 策略
        // TOP_SECRET 限制：仅 owner + ADMIN + 同部门员工 + allowedLevels=TOP_SECRET 授权用户可见
        //                  category grant 不释放 TOP_SECRET
        if (doc.getDocType() == DocumentType.RESEARCH) {
            // owner 自己全见
            if (doc.getOwner() != null && doc.getOwner().getId().equals(user.getId())) {
                return;
            }
            // 同部门员工本部门全见（含 TOP_SECRET，所有员工不限于部门负责人）
            if (doc.getOwner() != null
                    && doc.getOwner().getDepartment() != null
                    && user.getDepartment() != null
                    && doc.getOwner().getDepartment().getId().equals(user.getDepartment().getId())) {
                return;
            }
            // 用户被授权的保密等级（含 TOP_SECRET，由 ADMIN 显式授权，跨部门场景）
            if (doc.getConfidentialityLevel() != null
                    && dataVisibilityChecker.getAllowedLevels(user).contains(doc.getConfidentialityLevel())) {
                return;
            }
            // category grant：跨部门按分类授权（仅非 TOP_SECRET）
            if (doc.getConfidentialityLevel() != null
                    && doc.getConfidentialityLevel() != ConfidentialityLevel.TOP_SECRET
                    && doc.getCategory() != null
                    && dataVisibilityChecker.getAllowedCategoryIds(user).contains(doc.getCategory().getId())) {
                return;
            }
            // TOP_SECRET: 不允许通过 DocumentShare 分享，到此为止拒绝
            if (doc.getConfidentialityLevel() == ConfidentialityLevel.TOP_SECRET) {
                throw new SecurityException("该资料为绝密等级，仅所有者、管理员、同部门员工及被授权用户可访问");
            }
            // 被分享用户可见（非 TOP_SECRET）
            if (shareRepository.existsByDocumentIdAndSharedWithUserId(doc.getId(), user.getId())) {
                return;
            }
            throw new SecurityException("无权访问该研发资料");
        }
        // SYSTEM 类型：沿用原有可见性策略（不在本次改造范围）
        switch (doc.getVisibility()) {
            case PUBLIC:
                return;
            case DEPARTMENT:
                if (doc.getDepartment() == null || user.getDepartment() == null
                        || !doc.getDepartment().getId().equals(user.getDepartment().getId())) {
                    throw new SecurityException("无权访问该文档（部门限制）");
                }
                return;
            case ASSIGNEES:
                // SYSTEM 类型 ASSIGNEES: 仅上传人自己可见
                if (!doc.getUploader().getId().equals(user.getId())) {
                    throw new SecurityException("无权访问该文档（指定人员限制）");
                }
                return;
            default:
                throw new SecurityException("无权访问该文档");
        }
    }

    // ============ 文件校验 ============

    /**
     * 体系文档文件校验（向后兼容原调用）
     */
    private void validateFile(MultipartFile file) {
        validateFile(DocumentType.SYSTEM, file);
    }

    /**
     * 通用文件校验：根据文档类型选择对应白名单
     *
     * @param docType 文档类型（SYSTEM/RESEARCH）
     * @param file    上传的文件
     */
    private void validateFile(DocumentType docType, MultipartFile file) {
        if (file == null || file.isEmpty()) {
            throw new IllegalArgumentException("文件不能为空");
        }
        if (file.getSize() > MAX_FILE_SIZE) {
            throw new IllegalArgumentException("文件大小超过上限（50 MB）");
        }
        Set<String> allowedExt = (docType == DocumentType.RESEARCH)
                ? RESEARCH_ALLOWED_EXTENSIONS : SYSTEM_ALLOWED_EXTENSIONS;
        Set<String> allowedMime = (docType == DocumentType.RESEARCH)
                ? RESEARCH_ALLOWED_MIME_TYPES : SYSTEM_ALLOWED_MIME_TYPES;

        String ext = extractExtension(file.getOriginalFilename());
        if (ext == null || !allowedExt.contains(ext.toLowerCase())) {
            throw new IllegalArgumentException("不支持的文件类型: " + ext);
        }
        String mime = file.getContentType();
        if (mime == null || !allowedMime.contains(mime)) {
            throw new IllegalArgumentException("不支持的 MIME 类型: " + mime);
        }
    }

    private String extractExtension(String fileName) {
        if (fileName == null || !fileName.contains(".")) {
            return null;
        }
        return fileName.substring(fileName.lastIndexOf('.') + 1);
    }

    // ============ DTO 转换 ============

    private DocumentListDto toListDto(Document d) {
        return new DocumentListDto(
                d.getId(),
                d.getTitle(),
                d.getCategory() != null ? d.getCategory().getName() : null,
                d.getFileName(),
                d.getFileSize(),
                d.getFileType(),
                d.getFileExtension(),
                d.getVisibility() != null ? d.getVisibility().name() : null,
                d.getUploader() != null ? d.getUploader().getRealName() : null,
                d.getDepartment() != null ? d.getDepartment().getName() : null,
                d.getCreatedAt(),
                d.getVersion(),
                d.getStatus() != null ? d.getStatus().name() : null
        );
    }

    private DocumentDetailDto toDetailDto(Document d) {
        DocumentDetailDto dto = new DocumentDetailDto();
        dto.setId(d.getId());
        dto.setTitle(d.getTitle());
        dto.setDescription(d.getDescription());
        dto.setFileName(d.getFileName());
        dto.setFileSize(d.getFileSize());
        dto.setFileType(d.getFileType());
        dto.setFileExtension(d.getFileExtension());
        dto.setVisibility(d.getVisibility() != null ? d.getVisibility().name() : null);
        dto.setCategoryId(d.getCategory() != null ? d.getCategory().getId() : null);
        dto.setCategoryName(d.getCategory() != null ? d.getCategory().getName() : null);
        dto.setCategoryCode(d.getCategory() != null ? d.getCategory().getCode() : null);
        dto.setUploaderId(d.getUploader() != null ? d.getUploader().getId() : null);
        dto.setUploaderName(d.getUploader() != null ? d.getUploader().getRealName() : null);
        dto.setDepartmentId(d.getDepartment() != null ? d.getDepartment().getId() : null);
        dto.setDepartmentName(d.getDepartment() != null ? d.getDepartment().getName() : null);
        dto.setCreatedAt(d.getCreatedAt());
        dto.setUpdatedAt(d.getUpdatedAt());
        // 版本控制字段
        dto.setVersion(d.getVersion());
        dto.setStatus(d.getStatus() != null ? d.getStatus().name() : null);
        dto.setEffectiveDate(d.getEffectiveDate());
        dto.setObsoleteDate(d.getObsoleteDate());
        return dto;
    }

    // ========================================================================
    // ============ 研发资料（Research Material）业务方法 ==================
    // ========================================================================

    /**
     * 研发资料列表查询
     *
     * 权限矩阵（统一可见性规则 + SHARED 策略）：
     *  - ADMIN       : 可见全部（合规优先）
     *  - owner       : 自己录入的全见（含 TOP_SECRET）
     *  - 同部门员工  : 本部门他人数据全见（含 TOP_SECRET，所有员工）
     *  - 普通员工    : 自己录入的 + 本部门他人 + allowedLevels 内他人数据 + 被分享给自己的（默认空集 = 自己 + 本部门）
     *
     * @param view "mine"=我的资料 / "shared"=分享给我的 / "all"=全部（ADMIN） / 其他=统一规则+分享
     */
    @Transactional(readOnly = true)
    public Page<ResearchMaterialListDto> listResearchMaterials(int page, int size,
                                                                Long categoryId, String keyword,
                                                                String view, User currentUser) {
        PageRequest pr = PageRequest.of(page, size, Sort.by(Sort.Direction.DESC, "createdAt"));
        String kw = (keyword != null && !keyword.isBlank()) ? keyword.trim() : null;

        // 解析 view 参数（委托 DataVisibilityChecker，非 ADMIN 请求 all 自动降级）
        String fView = dataVisibilityChecker.resolveView(view, currentUser);
        final Long userId = currentUser.getId();

        Specification<Document> spec = (root, query, cb) -> {
            if (query.getResultType() != Long.class && query.getResultType() != long.class) {
                root.fetch("category", JoinType.LEFT);
                root.fetch("owner", JoinType.LEFT).fetch("department", JoinType.LEFT);
                query.distinct(true);
            }

            List<Predicate> predicates = new ArrayList<>();
            // 只查 RESEARCH 类型
            predicates.add(cb.equal(root.get("docType"), DocumentType.RESEARCH));

            if (categoryId != null) {
                predicates.add(cb.equal(root.get("category").get("id"), categoryId));
            }

            if (kw != null) {
                predicates.add(cb.like(cb.lower(root.get("title")), "%" + kw.toLowerCase() + "%"));
            }

            // 视图过滤
            if ("all".equals(fView)) {
                // ADMIN 看全部，不加条件
            } else if ("mine".equals(fView)) {
                // 我的资料：owner_id = 当前用户
                predicates.add(cb.equal(root.get("owner").get("id"), userId));
            } else if ("shared".equals(fView)) {
                // 仅看分享给我的：document_id IN (SELECT document_id FROM t_document_share WHERE shared_with_user_id = ?)
                jakarta.persistence.criteria.Subquery<Long> sq = query.subquery(Long.class);
                jakarta.persistence.criteria.Root<DocumentShare> dsRoot = sq.from(DocumentShare.class);
                sq.select(dsRoot.get("documentId"))
                  .where(cb.equal(dsRoot.get("sharedWithUserId"), userId));
                predicates.add(root.get("id").in(sq));
            } else {
                // 默认：统一可见性规则（owner + 同部门 + allowedLevels + category grant）OR 分享给我的
                Predicate visibilityPred = dataVisibilityChecker.buildVisibilityPredicate(
                        root, query, cb, currentUser, true);
                jakarta.persistence.criteria.Subquery<Long> sq = query.subquery(Long.class);
                jakarta.persistence.criteria.Root<DocumentShare> dsRoot = sq.from(DocumentShare.class);
                sq.select(dsRoot.get("documentId"))
                  .where(cb.equal(dsRoot.get("sharedWithUserId"), userId));
                Predicate sharedPred = root.get("id").in(sq);
                predicates.add(cb.or(visibilityPred, sharedPred));
            }

            return cb.and(predicates.toArray(new Predicate[0]));
        };

        Page<Document> docs = documentRepository.findAll(spec, pr);
        return docs.map(d -> toResearchListDto(d, currentUser));
    }

    /**
     * 研发资料详情
     */
    @Transactional(readOnly = true)
    public ResearchMaterialDetailDto getResearchMaterialDetail(Long id, User currentUser) {
        Document doc = documentRepository.findById(id)
                .orElseThrow(() -> new IllegalArgumentException("研发资料不存在"));
        if (doc.getDocType() != DocumentType.RESEARCH) {
            throw new IllegalArgumentException("该文档不是研发资料");
        }
        checkVisibility(doc, currentUser);
        return toResearchDetailDto(doc, currentUser);
    }

    /**
     * 上传研发资料
     *
     * 权限：任意已登录用户均可上传（Controller 层无 @PreAuthorize 限制）
     * 设置：docType=RESEARCH, owner=上传人, visibility=ASSIGNEES（仅 owner + 被分享人可见）
     */
    @Transactional
    public ResearchMaterialDetailDto uploadResearchMaterial(MultipartFile file, String title,
                                                             Long categoryId, String description,
                                                             String confidentialityLevel,
                                                             String sourceProvenanceJson,
                                                             User uploader) {
        // 1. 文件校验（使用研发资料白名单）
        validateFile(DocumentType.RESEARCH, file);

        // 2. 校验分类（必须为 RESEARCH 类型分类）
        DocumentCategory category = categoryRepository.findById(categoryId)
                .orElseThrow(() -> new IllegalArgumentException("分类不存在"));
        if (category.getDocType() != DocumentType.RESEARCH) {
            throw new IllegalArgumentException("分类不属于研发资料");
        }

        // 3. 解析保密等级（默认 INTERNAL）
        ConfidentialityLevel level = ConfidentialityLevel.INTERNAL;
        if (confidentialityLevel != null && !confidentialityLevel.isBlank()) {
            level = ConfidentialityLevel.valueOf(confidentialityLevel.toUpperCase());
        }

        // 4. 解析 sourceProvenance（仅原理文档分类需要）
        java.util.Map<String, Object> sourceProvenance = parseSourceProvenance(
                sourceProvenanceJson, category.getCode());

        // 4. 提取文件信息
        String originalName = file.getOriginalFilename();
        String extension = extractExtension(originalName);
        String mimeType = file.getContentType();
        long size = file.getSize();

        // 5. 读取文件内容并计算 checksum
        byte[] content;
        try {
            content = file.getBytes();
        } catch (IOException e) {
            throw new IllegalStateException("读取文件失败: " + e.getMessage(), e);
        }
        String checksum = ChecksumUtil.sha256(content);

        // 6. 保存文档元数据
        Document doc = new Document();
        doc.setTitle(title);
        doc.setDescription(description);
        doc.setFileName(originalName);
        doc.setFileSize(size);
        doc.setFileType(mimeType);
        doc.setFileExtension(extension);
        doc.setDocType(DocumentType.RESEARCH);
        doc.setOwner(uploader);
        doc.setConfidentialityLevel(level);
        // RESEARCH 资料复用 uploader 字段做审计追踪，但权限以 owner 为准
        doc.setUploader(uploader);
        // RESEARCH 资料固定使用 ASSIGNEES 可见性（实际可见性由 t_document_share 控制）
        doc.setVisibility(DocumentVisibility.ASSIGNEES);
        doc.setCategory(category);
        doc.setSourceProvenance(sourceProvenance);
        documentRepository.save(doc);

        // 7. 保存 BLOB
        DocumentFile docFile = new DocumentFile(doc.getId(), content, checksum);
        fileRepository.save(docFile);

        // 8. 返回详情
        Document saved = documentRepository.findById(doc.getId()).orElseThrow();
        return toResearchDetailDto(saved, uploader);
    }

    /**
     * 更新研发资料元数据
     *
     * 权限：仅 owner 或 ADMIN
     */
    @Transactional
    public ResearchMaterialDetailDto updateResearchMaterial(Long id, DocumentUpdateRequest req,
                                                             User currentUser) {
        Document doc = documentRepository.findById(id)
                .orElseThrow(() -> new IllegalArgumentException("研发资料不存在"));
        if (doc.getDocType() != DocumentType.RESEARCH) {
            throw new IllegalArgumentException("该文档不是研发资料");
        }
        // 权限：owner / ADMIN / 该等级或分类 READ_WRITE 授权
        if (!dataVisibilityChecker.canModify(currentUser, doc.getOwner(),
                doc.getConfidentialityLevel(), doc.getCategory(), true)) {
            throw new SecurityException("无权修改该研发资料");
        }

        if (req.getTitle() != null && !req.getTitle().isBlank()) {
            doc.setTitle(req.getTitle());
        }
        if (req.getDescription() != null) {
            doc.setDescription(req.getDescription());
        }
        if (req.getCategoryId() != null) {
            DocumentCategory category = categoryRepository.findById(req.getCategoryId())
                    .orElseThrow(() -> new IllegalArgumentException("分类不存在"));
            if (category.getDocType() != DocumentType.RESEARCH) {
                throw new IllegalArgumentException("分类不属于研发资料");
            }
            doc.setCategory(category);
        }
        // RESEARCH 资料不允许通过 update 改 visibility（固定 ASSIGNEES）

        // 保密等级变更
        if (req.getConfidentialityLevel() != null && !req.getConfidentialityLevel().isBlank()) {
            ConfidentialityLevel newLevel = ConfidentialityLevel.valueOf(req.getConfidentialityLevel().toUpperCase());
            // 升级到 TOP_SECRET 时，清除现有分享记录（绝密不可分享）
            if (newLevel == ConfidentialityLevel.TOP_SECRET
                    && doc.getConfidentialityLevel() != ConfidentialityLevel.TOP_SECRET) {
                shareRepository.deleteByDocumentId(id);
            }
            doc.setConfidentialityLevel(newLevel);
        }

        // 来源溯源变更（仅 RESEARCH 原理文档）
        if (req.getSourceProvenance() != null) {
            validateSourceProvenance(req.getSourceProvenance(),
                    doc.getCategory() != null ? doc.getCategory().getCode() : null);
            doc.setSourceProvenance(req.getSourceProvenance().isEmpty() ? null : req.getSourceProvenance());
        }

        Document saved = documentRepository.save(doc);
        return toResearchDetailDto(saved, currentUser);
    }

    /**
     * 删除研发资料
     *
     * 权限：仅 owner 或 ADMIN
     * 级联清理：t_document_share + t_document_file + t_document
     */
    @Transactional
    public void deleteResearchMaterial(Long id, User currentUser) {
        Document doc = documentRepository.findById(id)
                .orElseThrow(() -> new IllegalArgumentException("研发资料不存在"));
        if (doc.getDocType() != DocumentType.RESEARCH) {
            throw new IllegalArgumentException("该文档不是研发资料");
        }
        // 权限：owner / ADMIN / 该等级或分类 READ_WRITE 授权
        if (!dataVisibilityChecker.canModify(currentUser, doc.getOwner(),
                doc.getConfidentialityLevel(), doc.getCategory(), true)) {
            throw new SecurityException("无权删除该研发资料");
        }
        shareRepository.deleteByDocumentId(id);
        fileRepository.deleteByDocumentId(id);
        documentRepository.deleteById(id);
    }

    // ============ 分享管理 ============

    /**
     * 分享研发资料给指定同事
     *
     * 权限：仅 owner 可分享
     * 幂等：已存在的分享关系不重复创建
     */
    @Transactional
    public List<ShareDto> share(Long documentId, List<Long> userIds, User currentUser) {
        Document doc = documentRepository.findById(documentId)
                .orElseThrow(() -> new IllegalArgumentException("研发资料不存在"));
        if (doc.getDocType() != DocumentType.RESEARCH) {
            throw new IllegalArgumentException("该文档不是研发资料");
        }
        // 权限：仅 owner 可分享
        if (!dataVisibilityChecker.isAdmin(currentUser)
                && (doc.getOwner() == null || !doc.getOwner().getId().equals(currentUser.getId()))) {
            throw new SecurityException("仅资料所有者可分享");
        }
        // 绝密资料不可分享
        if (doc.getConfidentialityLevel() == ConfidentialityLevel.TOP_SECRET) {
            throw new IllegalStateException("绝密资料不可分享");
        }
        if (userIds == null || userIds.isEmpty()) {
            throw new IllegalArgumentException("请选择要分享的同事");
        }
        // 不能分享给自己
        if (userIds.contains(currentUser.getId())) {
            throw new IllegalArgumentException("不能分享给自己");
        }

        // 机密资料仅可分享给同部门同事
        boolean restrictToSameDept = (doc.getConfidentialityLevel() == ConfidentialityLevel.CONFIDENTIAL);
        Long ownerDeptId = (doc.getOwner() != null && doc.getOwner().getDepartment() != null)
                ? doc.getOwner().getDepartment().getId() : null;

        List<ShareDto> result = new ArrayList<>();
        for (Long targetUserId : userIds) {
            // 跳过不存在的用户
            Optional<User> targetOpt = userRepository.findById(targetUserId);
            if (targetOpt.isEmpty()) {
                continue;
            }
            User target = targetOpt.get();
            // 机密等级：仅同部门可分享
            if (restrictToSameDept) {
                Long targetDeptId = (target.getDepartment() != null) ? target.getDepartment().getId() : null;
                if (ownerDeptId == null || !ownerDeptId.equals(targetDeptId)) {
                    throw new SecurityException("机密资料仅可分享给同部门同事: " + target.getRealName());
                }
            }
            // 幂等：已存在则跳过
            if (shareRepository.existsByDocumentIdAndSharedWithUserId(documentId, targetUserId)) {
                continue;
            }
            DocumentShare share = new DocumentShare(documentId, targetUserId, currentUser.getId());
            shareRepository.save(share);

            // 通知被分享人
            notificationService.create(
                    targetUserId,
                    NotificationType.DOCUMENT_SHARE,
                    "文档分享",
                    currentUser.getRealName() + " 与您分享了研发资料《" + doc.getTitle() + "》",
                    "RESEARCH_MATERIAL", documentId, "/research-materials");

            result.add(new ShareDto(
                    share.getId(),
                    documentId,
                    targetUserId,
                    target.getRealName(),
                    target.getDepartment() != null ? target.getDepartment().getName() : null,
                    currentUser.getId(),
                    currentUser.getRealName(),
                    share.getCreatedAt()
            ));
        }
        return result;
    }

    /**
     * 取消分享
     *
     * 权限：仅 owner 可取消分享
     */
    @Transactional
    public void unshare(Long documentId, Long sharedWithUserId, User currentUser) {
        Document doc = documentRepository.findById(documentId)
                .orElseThrow(() -> new IllegalArgumentException("研发资料不存在"));
        if (doc.getDocType() != DocumentType.RESEARCH) {
            throw new IllegalArgumentException("该文档不是研发资料");
        }
        if (!dataVisibilityChecker.isAdmin(currentUser)
                && (doc.getOwner() == null || !doc.getOwner().getId().equals(currentUser.getId()))) {
            throw new SecurityException("仅资料所有者可取消分享");
        }
        shareRepository.deleteByDocumentIdAndSharedWithUserId(documentId, sharedWithUserId);
    }

    /**
     * 列出某研发资料的所有分享记录
     *
     * 权限：owner 或 ADMIN 可看全部；被分享人只看自己
     */
    @Transactional(readOnly = true)
    public List<ShareDto> listShares(Long documentId, User currentUser) {
        Document doc = documentRepository.findById(documentId)
                .orElseThrow(() -> new IllegalArgumentException("研发资料不存在"));
        if (doc.getDocType() != DocumentType.RESEARCH) {
            throw new IllegalArgumentException("该文档不是研发资料");
        }
        // 至少要有可见权限
        checkVisibility(doc, currentUser);

        List<DocumentShare> shares = shareRepository.findByDocumentId(documentId);
        List<ShareDto> result = new ArrayList<>();
        for (DocumentShare s : shares) {
            User target = userRepository.findById(s.getSharedWithUserId()).orElse(null);
            User sharer = userRepository.findById(s.getSharedByUserId()).orElse(null);
            result.add(new ShareDto(
                    s.getId(),
                    s.getDocumentId(),
                    s.getSharedWithUserId(),
                    target != null ? target.getRealName() : null,
                    target != null && target.getDepartment() != null ? target.getDepartment().getName() : null,
                    s.getSharedByUserId(),
                    sharer != null ? sharer.getRealName() : null,
                    s.getCreatedAt()
            ));
        }
        return result;
    }

    // ============ 研发资料 DTO 转换 ============

    private ResearchMaterialListDto toResearchListDto(Document d, User currentUser) {
        ResearchMaterialListDto dto = new ResearchMaterialListDto();
        dto.setId(d.getId());
        dto.setTitle(d.getTitle());
        dto.setCategoryName(d.getCategory() != null ? d.getCategory().getName() : null);
        dto.setFileName(d.getFileName());
        dto.setFileSize(d.getFileSize());
        dto.setFileType(d.getFileType());
        dto.setFileExtension(d.getFileExtension());
        dto.setOwnerId(d.getOwner() != null ? d.getOwner().getId() : null);
        dto.setOwnerName(d.getOwner() != null ? d.getOwner().getRealName() : null);
        dto.setOwnerDepartmentName(d.getOwner() != null && d.getOwner().getDepartment() != null
                ? d.getOwner().getDepartment().getName() : null);
        dto.setCreatedAt(d.getCreatedAt());
        dto.setVersion(d.getVersion());
        dto.setStatus(d.getStatus() != null ? d.getStatus().name() : null);
        dto.setConfidentialityLevel(d.getConfidentialityLevel() != null ? d.getConfidentialityLevel().name() : null);
        dto.setAccessRole(resolveAccessRole(d, currentUser));
        return dto;
    }

    private ResearchMaterialDetailDto toResearchDetailDto(Document d, User currentUser) {
        ResearchMaterialDetailDto dto = new ResearchMaterialDetailDto();
        dto.setId(d.getId());
        dto.setTitle(d.getTitle());
        dto.setDescription(d.getDescription());
        dto.setFileName(d.getFileName());
        dto.setFileSize(d.getFileSize());
        dto.setFileType(d.getFileType());
        dto.setFileExtension(d.getFileExtension());
        dto.setCategoryId(d.getCategory() != null ? d.getCategory().getId() : null);
        dto.setCategoryName(d.getCategory() != null ? d.getCategory().getName() : null);
        dto.setCategoryCode(d.getCategory() != null ? d.getCategory().getCode() : null);
        dto.setOwnerId(d.getOwner() != null ? d.getOwner().getId() : null);
        dto.setOwnerName(d.getOwner() != null ? d.getOwner().getRealName() : null);
        dto.setOwnerDepartmentName(d.getOwner() != null && d.getOwner().getDepartment() != null
                ? d.getOwner().getDepartment().getName() : null);
        dto.setCreatedAt(d.getCreatedAt());
        dto.setUpdatedAt(d.getUpdatedAt());
        dto.setVersion(d.getVersion());
        dto.setStatus(d.getStatus() != null ? d.getStatus().name() : null);
        dto.setEffectiveDate(d.getEffectiveDate());
        dto.setObsoleteDate(d.getObsoleteDate());
        dto.setConfidentialityLevel(d.getConfidentialityLevel() != null ? d.getConfidentialityLevel().name() : null);
        dto.setSourceProvenance(d.getSourceProvenance());
        dto.setAccessRole(resolveAccessRole(d, currentUser));
        return dto;
    }

    /**
     * 解析当前用户对该研发资料的访问角色
     *  - admin: ADMIN
     *  - owner: 我的资料
     *  - leader: 部门负责人（本部门他人记录）
     *  - shared: 分享给我的
     *  - viewer: 仅可查看（被授权等级）
     */
    private String resolveAccessRole(Document d, User currentUser) {
        if (dataVisibilityChecker.isAdmin(currentUser)) {
            return "admin";
        }
        if (d.getOwner() != null && d.getOwner().getId().equals(currentUser.getId())) {
            return "owner";
        }
        if (dataVisibilityChecker.isDeptLeader(currentUser)) {
            return "leader";
        }
        if (shareRepository.existsByDocumentIdAndSharedWithUserId(d.getId(), currentUser.getId())) {
            return "shared";
        }
        return "viewer";
    }

    // ============ 来源溯源（sourceProvenance）辅助方法 ============

    private static final Set<String> PRINCIPLE_CATEGORY_CODES = Set.of(
            "FACTORY_PROCESS", "THIRD_PARTY_PRINCIPLE", "COMMON_PRINCIPLE"
    );

    private static final Set<String> VALID_ORIGIN_VALUES = Set.of(
            "FACTORY", "THIRD_PARTY", "COMMON"
    );

    /**
     * 解析上传时传入的 sourceProvenance JSON 字符串
     *
     * @param json       可选，JSON 字符串，如：
     *                   {"origin":"FACTORY","thirdPartyName":"","obtainedDate":"","agreementNo":""}
     * @param categoryCode 当前分类编码（用于判断是否为原理文档分类）
     * @return 解析后的 Map，非原理文档分类时返回 null
     */
    private java.util.Map<String, Object> parseSourceProvenance(String json, String categoryCode) {
        if (json == null || json.isBlank()) {
            // 原理文档分类未提供 sourceProvenance：允许，但 THIRD_PARTY_PRINCIPLE 需提示
            return null;
        }
        if (categoryCode == null || !PRINCIPLE_CATEGORY_CODES.contains(categoryCode)) {
            throw new IllegalArgumentException(
                    "sourceProvenance 仅适用于原理文档分类（FACTORY_PROCESS/THIRD_PARTY_PRINCIPLE/COMMON_PRINCIPLE），当前分类: " + categoryCode);
        }
        try {
            com.fasterxml.jackson.databind.ObjectMapper mapper = new com.fasterxml.jackson.databind.ObjectMapper();
            @SuppressWarnings("unchecked")
            java.util.Map<String, Object> map = mapper.readValue(json, java.util.Map.class);
            validateSourceProvenance(map, categoryCode);
            return map;
        } catch (com.fasterxml.jackson.core.JsonProcessingException e) {
            throw new IllegalArgumentException("sourceProvenance JSON 解析失败: " + e.getMessage());
        }
    }

    /**
     * 校验 sourceProvenance Map 内容
     *   - origin 必填，且为 FACTORY/THIRD_PARTY/COMMON 之一
     *   - THIRD_PARTY_PRINCIPLE 分类必须填 thirdPartyName
     */
    private void validateSourceProvenance(java.util.Map<String, Object> map, String categoryCode) {
        if (map == null || map.isEmpty()) {
            return;
        }
        Object originObj = map.get("origin");
        if (originObj == null || originObj.toString().isBlank()) {
            throw new IllegalArgumentException("sourceProvenance.origin 不能为空");
        }
        String origin = originObj.toString().toUpperCase();
        if (!VALID_ORIGIN_VALUES.contains(origin)) {
            throw new IllegalArgumentException(
                    "sourceProvenance.origin 无效: " + origin + "，可选值: " + VALID_ORIGIN_VALUES);
        }
        if ("THIRD_PARTY_PRINCIPLE".equals(categoryCode)) {
            Object name = map.get("thirdPartyName");
            if (name == null || name.toString().isBlank()) {
                throw new IllegalArgumentException(
                        "THIRD_PARTY_PRINCIPLE 分类必须填写 sourceProvenance.thirdPartyName");
            }
        }
    }
}
