package com.insulinpump.usermgmt.controller;

import com.insulinpump.usermgmt.dto.*;
import com.insulinpump.usermgmt.model.Document;
import com.insulinpump.usermgmt.model.DocumentFile;
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
 * 研发资料 Controller
 *
 * 与 DocumentController（体系文档）的区别：
 *  - 上传权限：任意已登录用户（无 @PreAuthorize 限制）
 *  - 可见性：owner + 被分享用户（DocumentShare 表）+ ADMIN 全见
 *  - 文件白名单：更宽松（支持 ppt/txt/csv/md/zip 等）
 *
 * 权限矩阵：
 *  - GET    /api/research-materials              登录用户（受 owner/shared 约束）
 *  - GET    /api/research-materials/{id}         登录用户（受可见性约束）
 *  - POST   /api/research-materials/upload       登录用户
 *  - PUT    /api/research-materials/{id}         owner 或 ADMIN
 *  - DELETE /api/research-materials/{id}         owner 或 ADMIN
 *  - GET    /api/research-materials/{id}/download 登录用户（受可见性约束）
 *  - GET    /api/research-materials/{id}/preview  登录用户（受可见性约束）
 *  - POST   /api/research-materials/{id}/share   owner 或 ADMIN
 *  - DELETE /api/research-materials/{id}/share/{userId} owner 或 ADMIN
 *  - GET    /api/research-materials/{id}/shares  登录用户（受可见性约束）
 */
@RestController
@RequestMapping("/api/research-materials")
public class ResearchMaterialController {

    private final DocumentService documentService;

    public ResearchMaterialController(DocumentService documentService) {
        this.documentService = documentService;
    }

    /**
     * 研发资料列表
     *
     * @param view     "mine"=我的资料 / "shared"=分享给我的 / "all"=全部（仅 ADMIN）
     * @param categoryId 分类 ID（可选）
     * @param keyword   标题关键词（可选）
     */
    @GetMapping
    public ResponseEntity<ApiResponse<Page<ResearchMaterialListDto>>> list(
            @AuthenticationPrincipal User currentUser,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size,
            @RequestParam(required = false) Long categoryId,
            @RequestParam(required = false) String keyword,
            @RequestParam(defaultValue = "mine") String view) {
        Page<ResearchMaterialListDto> result = documentService.listResearchMaterials(
                page, size, categoryId, keyword, view, currentUser);
        return ResponseEntity.ok(ApiResponse.success(result));
    }

    /**
     * 研发资料详情
     */
    @GetMapping("/{id}")
    public ResponseEntity<ApiResponse<ResearchMaterialDetailDto>> getById(
            @PathVariable Long id,
            @AuthenticationPrincipal User currentUser) {
        ResearchMaterialDetailDto dto = documentService.getResearchMaterialDetail(id, currentUser);
        return ResponseEntity.ok(ApiResponse.success(dto));
    }

    /**
     * 上传研发资料
     *
     * 权限：任意已登录用户
     *
     * @param sourceProvenanceJson 可选，仅原理文档分类（FACTORY_PROCESS/THIRD_PARTY_PRINCIPLE/COMMON_PRINCIPLE）使用
     *        JSON 格式：{"origin":"FACTORY","thirdPartyName":"","obtainedDate":"2026-08-04","agreementNo":""}
     */
    @PostMapping("/upload")
    public ResponseEntity<ApiResponse<ResearchMaterialDetailDto>> upload(
            @RequestParam("file") MultipartFile file,
            @RequestParam("title") String title,
            @RequestParam("categoryId") Long categoryId,
            @RequestParam(value = "description", required = false) String description,
            @RequestParam(value = "confidentialityLevel", required = false, defaultValue = "INTERNAL") String confidentialityLevel,
            @RequestParam(value = "sourceProvenanceJson", required = false) String sourceProvenanceJson,
            @AuthenticationPrincipal User currentUser) {
        ResearchMaterialDetailDto dto = documentService.uploadResearchMaterial(
                file, title, categoryId, description, confidentialityLevel,
                sourceProvenanceJson, currentUser);
        return ResponseEntity.ok(ApiResponse.success("上传成功", dto));
    }

    /**
     * 更新研发资料元数据
     */
    @PutMapping("/{id}")
    public ResponseEntity<ApiResponse<ResearchMaterialDetailDto>> update(
            @PathVariable Long id,
            @RequestBody DocumentUpdateRequest req,
            @AuthenticationPrincipal User currentUser) {
        ResearchMaterialDetailDto dto = documentService.updateResearchMaterial(id, req, currentUser);
        return ResponseEntity.ok(ApiResponse.success("更新成功", dto));
    }

    /**
     * 删除研发资料
     */
    @DeleteMapping("/{id}")
    public ResponseEntity<ApiResponse<Void>> delete(
            @PathVariable Long id,
            @AuthenticationPrincipal User currentUser) {
        documentService.deleteResearchMaterial(id, currentUser);
        return ResponseEntity.ok(ApiResponse.success("删除成功", null));
    }

    /**
     * 下载研发资料
     */
    @GetMapping("/{id}/download")
    public ResponseEntity<Resource> download(
            @PathVariable Long id,
            @AuthenticationPrincipal User currentUser) {
        DocumentFile docFile = documentService.getFileContent(id, currentUser);
        return buildFileResponse(docFile, "attachment");
    }

    /**
     * 预览研发资料
     */
    @GetMapping("/{id}/preview")
    public ResponseEntity<Resource> preview(
            @PathVariable Long id,
            @AuthenticationPrincipal User currentUser) {
        DocumentFile docFile = documentService.getFileContent(id, currentUser);
        return buildFileResponse(docFile, "inline");
    }

    // ============ 分享管理 ============

    /**
     * 分享研发资料给指定同事（支持批量）
     */
    @PostMapping("/{id}/share")
    public ResponseEntity<ApiResponse<List<ShareDto>>> share(
            @PathVariable("id") Long documentId,
            @RequestBody ShareRequest req,
            @AuthenticationPrincipal User currentUser) {
        List<ShareDto> shares = documentService.share(documentId, req.getUserIds(), currentUser);
        return ResponseEntity.ok(ApiResponse.success("分享成功", shares));
    }

    /**
     * 取消分享
     */
    @DeleteMapping("/{id}/share/{userId}")
    public ResponseEntity<ApiResponse<Void>> unshare(
            @PathVariable("id") Long documentId,
            @PathVariable Long userId,
            @AuthenticationPrincipal User currentUser) {
        documentService.unshare(documentId, userId, currentUser);
        return ResponseEntity.ok(ApiResponse.success("取消分享成功", null));
    }

    /**
     * 列出某研发资料的所有分享记录
     */
    @GetMapping("/{id}/shares")
    public ResponseEntity<ApiResponse<List<ShareDto>>> listShares(
            @PathVariable("id") Long documentId,
            @AuthenticationPrincipal User currentUser) {
        List<ShareDto> shares = documentService.listShares(documentId, currentUser);
        return ResponseEntity.ok(ApiResponse.success(shares));
    }

    // ============ 私有辅助方法 ============

    /**
     * 构建文件响应（流式输出 + 文件名净化）
     * 与 DocumentController.buildFileResponse 逻辑一致
     */
    private ResponseEntity<Resource> buildFileResponse(DocumentFile docFile, String disposition) {
        Document doc = documentService.getDocumentRaw(docFile.getDocumentId());
        String fileName = doc.getFileName();
        String mimeType = doc.getFileType();

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
