package com.insulinpump.usermgmt.controller;

import com.insulinpump.usermgmt.dto.*;
import com.insulinpump.usermgmt.model.Document;
import com.insulinpump.usermgmt.model.DocumentFile;
import com.insulinpump.usermgmt.model.DocumentRevision;
import com.insulinpump.usermgmt.model.DocumentVisibility;
import com.insulinpump.usermgmt.model.User;
import com.insulinpump.usermgmt.service.DocumentService;
import org.springframework.core.io.InputStreamResource;
import org.springframework.core.io.Resource;
import org.springframework.data.domain.Page;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

import java.io.ByteArrayInputStream;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.List;

/**
 * 文档管理 Controller
 *
 * 权限矩阵：
 *  - GET    /api/documents           登录用户
 *  - GET    /api/documents/{id}      登录用户（受可见性约束）
 *  - POST   /api/documents/upload    ADMIN, SYSTEM_ENGINEER
 *  - PUT    /api/documents/{id}      ADMIN, SYSTEM_ENGINEER（或上传人）
 *  - DELETE /api/documents/{id}      ADMIN
 *  - GET    /api/documents/{id}/download  登录用户（受可见性约束）
 *  - GET    /api/documents/{id}/preview   登录用户（受可见性约束）
 */
@RestController
@RequestMapping("/api/documents")
public class DocumentController {

    private final DocumentService documentService;

    public DocumentController(DocumentService documentService) {
        this.documentService = documentService;
    }

    @GetMapping
    public ResponseEntity<ApiResponse<Page<DocumentListDto>>> list(
            @AuthenticationPrincipal User currentUser,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size,
            @RequestParam(required = false) Long categoryId,
            @RequestParam(required = false) String keyword) {
        Page<DocumentListDto> result = documentService.listDocuments(
                page, size, categoryId, keyword, currentUser);
        return ResponseEntity.ok(ApiResponse.success(result));
    }

    @GetMapping("/{id}")
    public ResponseEntity<ApiResponse<DocumentDetailDto>> getById(
            @PathVariable Long id,
            @AuthenticationPrincipal User currentUser) {
        DocumentDetailDto dto = documentService.getDocumentDetail(id, currentUser);
        return ResponseEntity.ok(ApiResponse.success(dto));
    }

    @PostMapping("/upload")
    @PreAuthorize("hasAnyRole('ADMIN','SYSTEM_ENGINEER')")
    public ResponseEntity<ApiResponse<DocumentDetailDto>> upload(
            @RequestParam("file") MultipartFile file,
            @RequestParam("title") String title,
            @RequestParam("categoryId") Long categoryId,
            @RequestParam(value = "description", required = false) String description,
            @RequestParam(value = "visibility", defaultValue = "PUBLIC") String visibility,
            @AuthenticationPrincipal User currentUser) {
        DocumentVisibility v = DocumentVisibility.valueOf(visibility.toUpperCase());
        DocumentDetailDto dto = documentService.upload(
                file, title, categoryId, description, v, currentUser);
        return ResponseEntity.ok(ApiResponse.success("上传成功", dto));
    }

    @PutMapping("/{id}")
    @PreAuthorize("hasAnyRole('ADMIN','SYSTEM_ENGINEER')")
    public ResponseEntity<ApiResponse<DocumentDetailDto>> update(
            @PathVariable Long id,
            @RequestBody DocumentUpdateRequest req,
            @AuthenticationPrincipal User currentUser) {
        DocumentDetailDto dto = documentService.update(id, req, currentUser);
        return ResponseEntity.ok(ApiResponse.success("更新成功", dto));
    }

    @DeleteMapping("/{id}")
    @PreAuthorize("hasRole('ADMIN')")
    public ResponseEntity<ApiResponse<Void>> delete(
            @PathVariable Long id,
            @AuthenticationPrincipal User currentUser) {
        documentService.delete(id, currentUser);
        return ResponseEntity.ok(ApiResponse.success("删除成功", null));
    }

    @GetMapping("/{id}/download")
    public ResponseEntity<Resource> download(
            @PathVariable Long id,
            @AuthenticationPrincipal User currentUser) {
        DocumentFile docFile = documentService.getFileContent(id, currentUser);
        return buildFileResponse(docFile, "attachment");
    }

    @GetMapping("/{id}/preview")
    public ResponseEntity<Resource> preview(
            @PathVariable Long id,
            @AuthenticationPrincipal User currentUser) {
        DocumentFile docFile = documentService.getFileContent(id, currentUser);
        return buildFileResponse(docFile, "inline");
    }

    // ============ 版本控制端点 ============

    /**
     * 发布文档（首次发布或发布新版本）- 直接发布通道
     *
     * 权限: ADMIN, SYSTEM_ENGINEER（或上传人）
     * 状态转换: DRAFT -> PUBLISHED, PUBLISHED -> PUBLISHED(新版本)
     *
     * 注: 走审批流请用 submit-review -> approve。
     */
    @PostMapping("/{id}/publish")
    @PreAuthorize("hasAnyRole('ADMIN','SYSTEM_ENGINEER')")
    public ResponseEntity<ApiResponse<DocumentDetailDto>> publish(
            @PathVariable Long id,
            @RequestBody(required = false) PublishRequest req,
            @AuthenticationPrincipal User user) {
        // 合规：电子签名需要密码 + 签名含义（FDA Part 11）
        if (req == null || req.getPassword() == null || req.getPassword().isBlank()
                || req.getMeaning() == null || req.getMeaning().isBlank()) {
            throw new IllegalArgumentException("发布需要电子签名（password + meaning 必填）");
        }
        String changeLog = req.getChangeLog();
        DocumentDetailDto dto = documentService.publish(
                id, changeLog, user, req.getPassword(), req.getMeaning());
        return ResponseEntity.ok(ApiResponse.success("发布成功", dto));
    }

    // ============ 审批工作流端点 ============

    /**
     * 提交评审 - DRAFT -> REVIEW
     *
     * 权限: ADMIN, SYSTEM_ENGINEER（或上传人）
     */
    @PostMapping("/{id}/submit-review")
    @PreAuthorize("hasAnyRole('ADMIN','SYSTEM_ENGINEER')")
    public ResponseEntity<ApiResponse<DocumentDetailDto>> submitReview(
            @PathVariable Long id,
            @AuthenticationPrincipal User user) {
        DocumentDetailDto dto = documentService.submitForReview(id, user);
        return ResponseEntity.ok(ApiResponse.success("已提交评审", dto));
    }

    /**
     * 审批通过 - REVIEW -> PUBLISHED
     *
     * 权限: 仅 ADMIN
     */
    @PostMapping("/{id}/approve")
    @PreAuthorize("hasRole('ADMIN')")
    public ResponseEntity<ApiResponse<DocumentDetailDto>> approve(
            @PathVariable Long id,
            @RequestBody(required = false) ReviewDecisionRequest req,
            @AuthenticationPrincipal User user) {
        // 合规：电子签名需要密码 + 签名含义（FDA Part 11）
        if (req == null || req.getPassword() == null || req.getPassword().isBlank()
                || req.getMeaning() == null || req.getMeaning().isBlank()) {
            throw new IllegalArgumentException("审批需要电子签名（password + meaning 必填）");
        }
        String comment = req.getComment();
        DocumentDetailDto dto = documentService.approve(
                id, comment, user, req.getPassword(), req.getMeaning());
        return ResponseEntity.ok(ApiResponse.success("审批通过", dto));
    }

    /**
     * 审批驳回 - REVIEW -> DRAFT
     *
     * 权限: 仅 ADMIN
     * body.comment 必填（驳回必须给理由）
     */
    @PostMapping("/{id}/reject")
    @PreAuthorize("hasRole('ADMIN')")
    public ResponseEntity<ApiResponse<DocumentDetailDto>> reject(
            @PathVariable Long id,
            @RequestBody ReviewDecisionRequest req,
            @AuthenticationPrincipal User user) {
        // 合规：电子签名需要密码 + 签名含义（FDA Part 11）
        if (req == null || req.getPassword() == null || req.getPassword().isBlank()
                || req.getMeaning() == null || req.getMeaning().isBlank()) {
            throw new IllegalArgumentException("驳回需要电子签名（password + meaning 必填）");
        }
        String comment = req.getComment();
        DocumentDetailDto dto = documentService.reject(
                id, comment, user, req.getPassword(), req.getMeaning());
        return ResponseEntity.ok(ApiResponse.success("已驳回", dto));
    }

    /**
     * 作废 - PUBLISHED -> OBSOLETE
     *
     * 权限: 仅 ADMIN
     */
    @PostMapping("/{id}/retire")
    @PreAuthorize("hasRole('ADMIN')")
    public ResponseEntity<ApiResponse<DocumentDetailDto>> retire(
            @PathVariable Long id,
            @RequestBody(required = false) ReviewDecisionRequest req,
            @AuthenticationPrincipal User user) {
        // 合规：电子签名需要密码 + 签名含义（FDA Part 11）
        if (req == null || req.getPassword() == null || req.getPassword().isBlank()
                || req.getMeaning() == null || req.getMeaning().isBlank()) {
            throw new IllegalArgumentException("作废需要电子签名（password + meaning 必填）");
        }
        DocumentDetailDto dto = documentService.retire(
                id, user, req.getPassword(), req.getMeaning());
        return ResponseEntity.ok(ApiResponse.success("已作废", dto));
    }

    /**
     * 查询文档审批历史（按时间倒序）
     */
    @GetMapping("/{id}/reviews")
    public ResponseEntity<ApiResponse<List<ReviewRecordDto>>> listReviews(
            @PathVariable Long id,
            @AuthenticationPrincipal User user) {
        List<ReviewRecordDto> list = documentService.listReviews(id, user);
        return ResponseEntity.ok(ApiResponse.success(list));
    }


    /**
     * 获取文档修订历史（按发布时间倒序）
     */
    @GetMapping("/{id}/revisions")
    public ResponseEntity<ApiResponse<List<DocumentRevisionDto>>> listRevisions(
            @PathVariable Long id,
            @AuthenticationPrincipal User user) {
        List<DocumentRevisionDto> list = documentService.listRevisions(id, user);
        return ResponseEntity.ok(ApiResponse.success(list));
    }

    /**
     * 版本对比（元数据级 diff）
     *
     * @param id 文档 ID
     * @param from 源修订 ID
     * @param to 目标修订 ID
     */
    @GetMapping("/{id}/diff")
    public ResponseEntity<ApiResponse<DocumentDiffDto>> diff(
            @PathVariable Long id,
            @RequestParam Long from,
            @RequestParam Long to,
            @AuthenticationPrincipal User user) {
        DocumentDiffDto diffDto = documentService.diff(id, from, to, user);
        return ResponseEntity.ok(ApiResponse.success(diffDto));
    }

    /**
     * 回滚到指定版本（非破坏性，创建新版本）
     *
     * 权限: 仅 ADMIN
     */
    @PostMapping("/{id}/rollback/{revId}")
    @PreAuthorize("hasRole('ADMIN')")
    public ResponseEntity<ApiResponse<DocumentDetailDto>> rollback(
            @PathVariable Long id,
            @PathVariable Long revId,
            @RequestBody(required = false) ReviewDecisionRequest req,
            @AuthenticationPrincipal User user) {
        // 合规：电子签名需要密码 + 签名含义（FDA Part 11）
        if (req == null || req.getPassword() == null || req.getPassword().isBlank()
                || req.getMeaning() == null || req.getMeaning().isBlank()) {
            throw new IllegalArgumentException("回滚需要电子签名（password + meaning 必填）");
        }
        DocumentDetailDto dto = documentService.rollback(
                id, revId, user, req.getPassword(), req.getMeaning());
        return ResponseEntity.ok(ApiResponse.success("回滚成功", dto));
    }

    /**
     * 下载指定修订版本的文件内容
     */
    @GetMapping("/revisions/{revId}/download")
    public ResponseEntity<Resource> downloadRevision(
            @PathVariable Long revId,
            @RequestParam Long documentId,
            @AuthenticationPrincipal User user) {
        DocumentRevision rev = documentService.getRevision(documentId, revId, user);
        String encodedName = URLEncoder.encode(rev.getFileName(), StandardCharsets.UTF_8)
                .replace("+", "%20");
        InputStreamResource resource = new InputStreamResource(
                new ByteArrayInputStream(rev.getContentSnapshot()));
        return ResponseEntity.ok()
                .header(HttpHeaders.CONTENT_DISPOSITION,
                        "attachment; filename*=UTF-8''" + encodedName)
                .contentType(MediaType.parseMediaType(rev.getFileType()))
                .contentLength(rev.getContentSnapshot().length)
                .body(resource);
    }

    /**
     * 构建文件响应（流式输出 + 文件名净化）
     *
     * @param docFile 文件内容
     * @param disposition "attachment"=下载, "inline"=预览
     */
    private ResponseEntity<Resource> buildFileResponse(DocumentFile docFile, String disposition) {
        // 获取文档元数据中的文件名与 MIME 类型
        Document doc = documentService.getDocumentRaw(docFile.getDocumentId());
        String fileName = doc.getFileName();
        String mimeType = doc.getFileType();

        // 文件名净化：URLEncoder + RFC 5987 filename* 格式，防止路径穿越与中文乱码
        String encodedName = URLEncoder.encode(fileName, StandardCharsets.UTF_8)
                .replace("+", "%20");

        InputStreamResource resource = new InputStreamResource(
                new ByteArrayInputStream(docFile.getContent()));

        return ResponseEntity.ok()
                .header(HttpHeaders.CONTENT_DISPOSITION,
                        disposition + "; filename*=UTF-8''" + encodedName)
                .contentType(MediaType.parseMediaType(mimeType))
                .contentLength(docFile.getContent().length)
                .body(resource);
    }
}
