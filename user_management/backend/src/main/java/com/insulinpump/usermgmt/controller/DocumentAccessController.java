package com.insulinpump.usermgmt.controller;

import com.insulinpump.usermgmt.dto.ApiResponse;
import com.insulinpump.usermgmt.dto.DocumentAccessDto;
import com.insulinpump.usermgmt.dto.DocumentAccessRequest;
import com.insulinpump.usermgmt.model.ConfidentialityLevel;
import com.insulinpump.usermgmt.model.Document;
import com.insulinpump.usermgmt.model.DocumentShare;
import com.insulinpump.usermgmt.model.DocumentType;
import com.insulinpump.usermgmt.model.NotificationType;
import com.insulinpump.usermgmt.model.User;
import com.insulinpump.usermgmt.repository.DocumentRepository;
import com.insulinpump.usermgmt.repository.DocumentShareRepository;
import com.insulinpump.usermgmt.repository.UserRepository;
import com.insulinpump.usermgmt.service.NotificationService;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

/**
 * 按资料授权 Controller（用户级，ADMIN 授权某员工查看某份具体研发资料）
 *
 * 复用 t_document_share 表（与 owner 分享同源）：管理员授权即写入一条
 * (document_id, user_id, admin_id) 分享记录，可见性判定/列表/通知自动生效。
 * 与保密等级授权、资料分类授权并列，构成"按资料"的细粒度授权。
 *
 * 权限矩阵：
 *  - GET    /api/users/{id}/document-access            ADMIN 或本人查询自己的资料授权
 *  - PUT    /api/users/{id}/document-access            ADMIN（user:assign-document）批量授予
 *  - DELETE /api/users/{id}/document-access/{docId}    ADMIN（user:assign-document）撤销单个
 *
 * 校验：
 *  - 仅 RESEARCH 资料可授权；SYSTEM 文档与 TOP_SECRET 资料整批拒绝
 *  - 幂等：已存在的授权跳过，不报错
 */
@RestController
@RequestMapping("/api/users/{userId}/document-access")
public class DocumentAccessController {

    private final DocumentShareRepository shareRepository;
    private final DocumentRepository documentRepository;
    private final UserRepository userRepository;
    private final NotificationService notificationService;

    public DocumentAccessController(DocumentShareRepository shareRepository,
                                    DocumentRepository documentRepository,
                                    UserRepository userRepository,
                                    NotificationService notificationService) {
        this.shareRepository = shareRepository;
        this.documentRepository = documentRepository;
        this.userRepository = userRepository;
        this.notificationService = notificationService;
    }

    /**
     * 查询某用户的全部按资料授权（含 owner 分享给该用户的资料）
     * 权限：ADMIN 或本人查询自己
     */
    @GetMapping
    public ResponseEntity<ApiResponse<List<DocumentAccessDto>>> list(
            @PathVariable Long userId,
            @AuthenticationPrincipal User currentUser) {
        if (!isAdmin(currentUser) && !userId.equals(currentUser.getId())) {
            throw new SecurityException("无权查询他人的资料授权");
        }
        userRepository.findById(userId)
                .orElseThrow(() -> new IllegalArgumentException("用户不存在"));

        return ResponseEntity.ok(ApiResponse.success(listFor(userId)));
    }

    /**
     * 批量授予某用户查看指定研发资料的权限（幂等：已存在的跳过）
     * 权限：ADMIN（user:assign-document）
     *
     * 校验：
     *  - documentIds 非空
     *  - 所有文档必须存在且为 RESEARCH 类型（SYSTEM 文档 / TOP_SECRET 整批拒绝）
     *  - 已存在的授权跳过
     *
     * 返回：该用户当前全部按资料授权
     */
    @PutMapping
    @PreAuthorize("hasAuthority('user:assign-document')")
    public ResponseEntity<ApiResponse<List<DocumentAccessDto>>> grant(
            @PathVariable Long userId,
            @RequestBody DocumentAccessRequest req,
            @AuthenticationPrincipal User currentUser) {
        userRepository.findById(userId)
                .orElseThrow(() -> new IllegalArgumentException("用户不存在"));

        if (req.getDocumentIds() == null || req.getDocumentIds().isEmpty()) {
            throw new IllegalArgumentException("文档 ID 列表不能为空");
        }

        // 去重
        Set<Long> requestedIds = new HashSet<>(req.getDocumentIds());

        // 一次性查询所有文档，校验存在性 + RESEARCH 类型 + 非 TOP_SECRET
        List<Document> documents = documentRepository.findAllById(requestedIds);
        if (documents.size() != requestedIds.size()) {
            throw new IllegalArgumentException("部分文档不存在");
        }
        for (Document doc : documents) {
            if (doc.getDocType() != DocumentType.RESEARCH) {
                throw new IllegalArgumentException("仅可授权 RESEARCH 研发资料，文档《"
                        + doc.getTitle() + "》不是研发资料");
            }
            if (doc.getConfidentialityLevel() == ConfidentialityLevel.TOP_SECRET) {
                throw new IllegalArgumentException("绝密资料不可按资料授权"
                        + "（请改用保密等级授权开放）");
            }
        }

        // 幂等写入：已存在的跳过，通知被授权员工
        int grantedCount = 0;
        for (Document doc : documents) {
            if (!shareRepository.existsByDocumentIdAndSharedWithUserId(doc.getId(), userId)) {
                shareRepository.save(new DocumentShare(doc.getId(), userId, currentUser.getId()));
                grantedCount++;
                notificationService.create(
                        userId,
                        NotificationType.DOCUMENT_SHARE,
                        "资料授权",
                        "管理员授予您查看研发资料《" + doc.getTitle() + "》的权限",
                        "RESEARCH_MATERIAL", doc.getId(), "/research-materials");
            }
        }

        return ResponseEntity.ok(ApiResponse.success(
                grantedCount + " 份资料授权成功", listFor(userId)));
    }

    /**
     * 撤销某用户的某份资料授权
     * 权限：ADMIN（user:assign-document）
     */
    @DeleteMapping("/{documentId}")
    @PreAuthorize("hasAuthority('user:assign-document')")
    public ResponseEntity<ApiResponse<Void>> revoke(
            @PathVariable Long userId,
            @PathVariable Long documentId,
            @AuthenticationPrincipal User currentUser) {
        userRepository.findById(userId)
                .orElseThrow(() -> new IllegalArgumentException("用户不存在"));

        shareRepository.deleteByDocumentIdAndSharedWithUserId(documentId, userId);
        return ResponseEntity.ok(ApiResponse.success("撤销成功", null));
    }

    private boolean isAdmin(User user) {
        return user != null
                && user.getRole() != null
                && "ADMIN".equals(user.getRole().getCode());
    }

    /**
     * 组装某用户的全部按资料授权清单
     */
    private List<DocumentAccessDto> listFor(Long userId) {
        List<DocumentShare> shares = shareRepository.findBySharedWithUserId(userId);
        List<DocumentAccessDto> result = new ArrayList<>();
        for (DocumentShare s : shares) {
            Document doc = documentRepository.findById(s.getDocumentId()).orElse(null);
            if (doc == null) {
                continue;
            }
            User grantor = userRepository.findById(s.getSharedByUserId()).orElse(null);
            DocumentAccessDto dto = new DocumentAccessDto();
            dto.setDocumentId(s.getDocumentId());
            dto.setDocumentTitle(doc.getTitle());
            dto.setCategoryId(doc.getCategory() != null ? doc.getCategory().getId() : null);
            dto.setCategoryName(doc.getCategory() != null ? doc.getCategory().getName() : null);
            dto.setCategoryCode(doc.getCategory() != null ? doc.getCategory().getCode() : null);
            dto.setConfidentialityLevel(doc.getConfidentialityLevel() != null
                    ? doc.getConfidentialityLevel().name() : null);
            dto.setGrantedByUserId(s.getSharedByUserId());
            dto.setGrantedByName(grantor != null ? grantor.getRealName() : null);
            dto.setGrantedAt(s.getCreatedAt());
            result.add(dto);
        }
        return result;
    }
}
