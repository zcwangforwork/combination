package com.insulinpump.usermgmt.service;

import com.insulinpump.usermgmt.model.*;
import com.insulinpump.usermgmt.repository.DocumentCategoryRepository;
import com.insulinpump.usermgmt.repository.DocumentFileRepository;
import com.insulinpump.usermgmt.repository.DocumentRepository;
import com.insulinpump.usermgmt.repository.DocumentReviewRepository;
import com.insulinpump.usermgmt.repository.DocumentRevisionRepository;
import com.insulinpump.usermgmt.repository.DocumentShareRepository;
import com.insulinpump.usermgmt.repository.UserRepository;
import com.insulinpump.usermgmt.util.ChecksumUtil;
import com.insulinpump.usermgmt.dto.DocumentDetailDto;
import com.insulinpump.usermgmt.dto.DocumentDiffDto;
import com.insulinpump.usermgmt.dto.DocumentRevisionDto;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.mockito.junit.jupiter.MockitoSettings;
import org.mockito.quality.Strictness;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.jpa.domain.Specification;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.web.multipart.MultipartFile;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Optional;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.*;

/**
 * DocumentService 单元测试
 *
 * 覆盖关键路径：
 *  - upload: happy path / 空文件 / 超大文件 / 非法类型 / 合法类型
 *  - getDocumentDetail: 正常 / 不存在 / 可见性拒绝
 *  - delete: 正常 / 非 ADMIN 拒绝
 *  - getFileContent: 正常 / BLOB 不存在（critical gap 修复验证）
 *  - listDocuments: ADMIN 看全部 / 非 ADMIN 受可见性过滤
 */
@ExtendWith(MockitoExtension.class)
@MockitoSettings(strictness = Strictness.LENIENT)
class DocumentServiceTest {

    @Mock
    private DocumentRepository documentRepository;

    @Mock
    private DocumentFileRepository fileRepository;

    @Mock
    private DocumentCategoryRepository categoryRepository;

    @Mock
    private DocumentRevisionRepository revisionRepository;

    @Mock
    private DocumentReviewRepository reviewRepository;

    @Mock
    private DocumentShareRepository shareRepository;

    @Mock
    private UserRepository userRepository;

    @Mock
    private DataVisibilityChecker dataVisibilityChecker;

    @Mock
    private SignatureService signatureService;

    @InjectMocks
    private DocumentService documentService;

    private User adminUser;
    private User normalUser;
    private User leaderUser;
    private User deptMember;
    private DocumentCategory category;
    private Department dept1;
    private Department dept2;

    @BeforeEach
    void setUp() {
        Role adminRole = new Role("管理员", "ADMIN", "");
        Role engineerRole = new Role("结构工程师", "STRUCTURAL_ENGINEER", "");

        dept1 = new Department("研发中心", "", null);
        dept1.setId(1L);
        dept2 = new Department("质量部", "", null);
        dept2.setId(2L);

        adminUser = new User();
        adminUser.setId(1L);
        adminUser.setUsername("admin");
        adminUser.setRole(adminRole);
        adminUser.setDepartment(dept1);

        normalUser = new User();
        normalUser.setId(2L);
        normalUser.setUsername("zhangsan");
        normalUser.setRole(engineerRole);
        normalUser.setDepartment(dept2);

        // 部门负责人（dept1 的 leader）
        leaderUser = new User();
        leaderUser.setId(3L);
        leaderUser.setUsername("leader");
        leaderUser.setRole(engineerRole);
        leaderUser.setDepartment(dept1);
        leaderUser.setDepartmentLeader(true);

        // dept1 的普通成员（非 leader）
        deptMember = new User();
        deptMember.setId(4L);
        deptMember.setUsername("member");
        deptMember.setRole(engineerRole);
        deptMember.setDepartment(dept1);
        deptMember.setDepartmentLeader(false);

        category = new DocumentCategory("PROCEDURE", "程序文件", "", 1);
        category.setId(1L);

        // DataVisibilityChecker mock 默认行为
        when(dataVisibilityChecker.isAdmin(adminUser)).thenReturn(true);
        when(dataVisibilityChecker.isAdmin(normalUser)).thenReturn(false);
        when(dataVisibilityChecker.isAdmin(leaderUser)).thenReturn(false);
        when(dataVisibilityChecker.isAdmin(deptMember)).thenReturn(false);
        when(dataVisibilityChecker.getAllowedLevels(any())).thenReturn(Set.of());
    }

    // ============ Upload Tests ============

    @Nested
    @DisplayName("upload() 上传文档")
    class UploadTests {

        @Test
        @DisplayName("正常上传 PDF 文档")
        void uploadPdfSuccess() {
            MockMultipartFile file = new MockMultipartFile(
                    "file", "test.pdf", "application/pdf", "PDF content".getBytes());

            when(categoryRepository.findById(1L)).thenReturn(Optional.of(category));
            when(documentRepository.save(any(Document.class))).thenAnswer(inv -> {
                Document d = inv.getArgument(0);
                d.setId(100L);
                return d;
            });
            when(fileRepository.save(any(DocumentFile.class))).thenAnswer(inv -> inv.getArgument(0));
            when(documentRepository.findById(100L)).thenReturn(Optional.of(buildSavedDoc()));

            var result = documentService.upload(file, "测试文档", 1L, "描述",
                    DocumentVisibility.PUBLIC, adminUser);

            assertNotNull(result);
            assertEquals("测试文档", result.getTitle());
            verify(documentRepository).save(any(Document.class));
            verify(fileRepository).save(any(DocumentFile.class));
        }

        @Test
        @DisplayName("空文件应被拒绝")
        void uploadEmptyFileRejected() {
            MockMultipartFile file = new MockMultipartFile(
                    "file", "empty.pdf", "application/pdf", new byte[0]);

            IllegalArgumentException ex = assertThrows(IllegalArgumentException.class, () ->
                    documentService.upload(file, "空文件", 1L, null,
                            DocumentVisibility.PUBLIC, adminUser));
            assertTrue(ex.getMessage().contains("不能为空"));
        }

        @Test
        @DisplayName("超过 50MB 文件应被拒绝")
        void uploadOversizedFileRejected() {
            byte[] bigContent = new byte[(int) (50L * 1024 * 1024 + 1)];
            MockMultipartFile file = new MockMultipartFile(
                    "file", "big.pdf", "application/pdf", bigContent);

            IllegalArgumentException ex = assertThrows(IllegalArgumentException.class, () ->
                    documentService.upload(file, "大文件", 1L, null,
                            DocumentVisibility.PUBLIC, adminUser));
            assertTrue(ex.getMessage().contains("超过上限"));
        }

        @Test
        @DisplayName("非法文件类型 .exe 应被拒绝")
        void uploadExeRejected() {
            MockMultipartFile file = new MockMultipartFile(
                    "file", "malware.exe", "application/octet-stream", "EXE".getBytes());

            IllegalArgumentException ex = assertThrows(IllegalArgumentException.class, () ->
                    documentService.upload(file, "病毒", 1L, null,
                            DocumentVisibility.PUBLIC, adminUser));
            assertTrue(ex.getMessage().contains("不支持的文件类型"));
        }

        @Test
        @DisplayName("Word .docx 文档可正常上传")
        void uploadDocxSuccess() {
            MockMultipartFile file = new MockMultipartFile(
                    "file", "doc.docx",
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    "DOCX".getBytes());

            when(categoryRepository.findById(1L)).thenReturn(Optional.of(category));
            when(documentRepository.save(any(Document.class))).thenAnswer(inv -> {
                Document d = inv.getArgument(0);
                d.setId(101L);
                return d;
            });
            when(fileRepository.save(any(DocumentFile.class))).thenAnswer(inv -> inv.getArgument(0));
            when(documentRepository.findById(101L)).thenReturn(Optional.of(buildSavedDoc()));

            assertDoesNotThrow(() ->
                    documentService.upload(file, "Word 文档", 1L, null,
                            DocumentVisibility.PUBLIC, adminUser));
        }
    }

    // ============ getDocumentDetail Tests ============

    @Nested
    @DisplayName("getDocumentDetail() 获取文档详情")
    class GetDetailTests {

        @Test
        @DisplayName("PUBLIC 文档任何登录用户可见")
        void publicDocVisibleToAll() {
            Document doc = buildSavedDoc();
            doc.setVisibility(DocumentVisibility.PUBLIC);
            when(documentRepository.findById(1L)).thenReturn(Optional.of(doc));

            assertDoesNotThrow(() -> documentService.getDocumentDetail(1L, normalUser));
        }

        @Test
        @DisplayName("文档不存在应抛异常")
        void docNotFound() {
            when(documentRepository.findById(999L)).thenReturn(Optional.empty());

            assertThrows(IllegalArgumentException.class, () ->
                    documentService.getDocumentDetail(999L, adminUser));
        }

        @Test
        @DisplayName("DEPARTMENT 文档跨部门用户被拒绝")
        void departmentVisibilityDenied() {
            Document doc = buildSavedDoc();
            doc.setVisibility(DocumentVisibility.DEPARTMENT);
            doc.setDepartment(dept1);  // 上传人在 dept1
            // normalUser 在 dept2
            when(documentRepository.findById(1L)).thenReturn(Optional.of(doc));

            SecurityException ex = assertThrows(SecurityException.class, () ->
                    documentService.getDocumentDetail(1L, normalUser));
            assertTrue(ex.getMessage().contains("部门限制"));
        }

        @Test
        @DisplayName("ADMIN 可访问任意可见性文档")
        void adminBypassVisibility() {
            Document doc = buildSavedDoc();
            doc.setVisibility(DocumentVisibility.DEPARTMENT);
            doc.setDepartment(dept2);  // admin 不在 dept2
            when(documentRepository.findById(1L)).thenReturn(Optional.of(doc));

            assertDoesNotThrow(() -> documentService.getDocumentDetail(1L, adminUser));
        }
    }

    // ============ Delete Tests ============

    @Nested
    @DisplayName("delete() 删除文档")
    class DeleteTests {

        @Test
        @DisplayName("ADMIN 可删除文档，BLOB 与元数据一并删除")
        void adminDeleteSuccess() {
            Document doc = buildSavedDoc();
            when(documentRepository.findById(1L)).thenReturn(Optional.of(doc));

            documentService.delete(1L, adminUser);

            verify(fileRepository).deleteByDocumentId(1L);
            verify(documentRepository).deleteById(1L);
        }

        @Test
        @DisplayName("非 ADMIN 删除被拒绝")
        void nonAdminDeleteDenied() {
            Document doc = buildSavedDoc();
            when(documentRepository.findById(1L)).thenReturn(Optional.of(normalUser.getId().equals(2L) ? doc : doc));

            assertThrows(SecurityException.class, () ->
                    documentService.delete(1L, normalUser));
            verify(fileRepository, never()).deleteByDocumentId(any());
            verify(documentRepository, never()).deleteById(any());
        }
    }

    // ============ getFileContent Tests ============

    @Nested
    @DisplayName("getFileContent() 获取文件内容")
    class GetFileContentTests {

        @Test
        @DisplayName("正常获取文件内容")
        void getFileContentSuccess() {
            Document doc = buildSavedDoc();
            doc.setVisibility(DocumentVisibility.PUBLIC);
            // 使用真实 SHA-256 checksum 以通过 ALCOA+ 校验
            byte[] content = "content".getBytes();
            String checksum = ChecksumUtil.sha256(content);
            DocumentFile df = new DocumentFile(1L, content, checksum);

            when(documentRepository.findById(1L)).thenReturn(Optional.of(doc));
            when(fileRepository.findByDocumentId(1L)).thenReturn(Optional.of(df));

            DocumentFile result = documentService.getFileContent(1L, normalUser);
            assertNotNull(result);
            assertEquals(checksum, result.getChecksum());
        }

        @Test
        @DisplayName("BLOB 已删除但元数据存在应抛异常（critical gap 修复验证）")
        void blobMissingThrowsException() {
            Document doc = buildSavedDoc();
            doc.setVisibility(DocumentVisibility.PUBLIC);

            when(documentRepository.findById(1L)).thenReturn(Optional.of(doc));
            when(fileRepository.findByDocumentId(1L)).thenReturn(Optional.empty());

            IllegalStateException ex = assertThrows(IllegalStateException.class, () ->
                    documentService.getFileContent(1L, normalUser));
            assertTrue(ex.getMessage().contains("文件内容不存在"));
        }
    }

    // ============ listDocuments Tests ============

    @Nested
    @DisplayName("listDocuments() 文档列表")
    class ListTests {

        @Test
        @DisplayName("ADMIN 调用 findAll（含 Specification）")
        void adminListCallsFindAll() {
            Page<Document> emptyPage = new PageImpl<>(List.of());
            when(documentRepository.findAll(any(Specification.class), any(PageRequest.class))).thenReturn(emptyPage);

            documentService.listDocuments(0, 20, null, null, adminUser);

            verify(documentRepository).findAll(any(Specification.class), any(PageRequest.class));
        }

        @Test
        @DisplayName("非 ADMIN 调用 findAll（含 Specification，带可见性过滤）")
        void nonAdminListCallsFindAll() {
            Page<Document> emptyPage = new PageImpl<>(List.of());
            when(documentRepository.findAll(any(Specification.class), any(PageRequest.class))).thenReturn(emptyPage);

            documentService.listDocuments(0, 20, null, null, normalUser);

            verify(documentRepository).findAll(any(Specification.class), any(PageRequest.class));
        }
    }

    // ============ Publish Tests ============

    @Nested
    @DisplayName("publish() 发布文档")
    class PublishTests {

        @Test
        @DisplayName("首次发布 DRAFT -> PUBLISHED v1.0")
        void firstPublishSuccess() {
            Document doc = buildSavedDoc();
            doc.setStatus(DocumentStatus.DRAFT);
            doc.setVersion(null);
            DocumentFile docFile = new DocumentFile(1L, "content".getBytes(), "abc123");

            when(documentRepository.findById(1L)).thenReturn(Optional.of(doc));
            when(fileRepository.findByDocumentId(1L)).thenReturn(Optional.of(docFile));
            when(documentRepository.save(any(Document.class))).thenAnswer(inv -> inv.getArgument(0));
            // 签名服务 mock（电子签名通过）
            when(signatureService.verifyAndRecord(any(), any(), any(), any(), any(), any()))
                    .thenReturn(new SignatureRecord());

            DocumentDetailDto result = documentService.publish(1L, "首次发布", adminUser, "pwd", "meaning");

            assertNotNull(result);
            assertEquals("v1.0", result.getVersion());
            assertEquals("PUBLISHED", result.getStatus());
            verify(revisionRepository).save(any(DocumentRevision.class));
        }

        @Test
        @DisplayName("再次发布 PUBLISHED -> PUBLISHED v1.1")
        void subsequentPublishSuccess() {
            Document doc = buildSavedDoc();
            doc.setStatus(DocumentStatus.PUBLISHED);
            doc.setVersion("v1.0");
            doc.setEffectiveDate(LocalDateTime.now().minusDays(1));
            DocumentFile docFile = new DocumentFile(1L, "content".getBytes(), "abc123");
            DocumentRevision prevRev = new DocumentRevision();
            prevRev.setId(10L);

            when(documentRepository.findById(1L)).thenReturn(Optional.of(doc));
            when(fileRepository.findByDocumentId(1L)).thenReturn(Optional.of(docFile));
            when(revisionRepository.findTopByDocumentIdOrderByPublishedAtDesc(1L))
                    .thenReturn(Optional.of(prevRev));
            when(revisionRepository.findById(10L)).thenReturn(Optional.of(prevRev));
            when(documentRepository.save(any(Document.class))).thenAnswer(inv -> inv.getArgument(0));
            // 签名服务 mock（电子签名通过）
            when(signatureService.verifyAndRecord(any(), any(), any(), any(), any(), any()))
                    .thenReturn(new SignatureRecord());

            DocumentDetailDto result = documentService.publish(1L, "修订内容", adminUser, "pwd", "meaning");

            assertEquals("v1.1", result.getVersion());
            assertEquals("PUBLISHED", result.getStatus());
            // 非首次发布: save 调用 2 次（新快照 + 标记前序 Revision 作废）
            verify(revisionRepository, atLeastOnce()).save(any(DocumentRevision.class));
        }

        @Test
        @DisplayName("OBSOLETE 状态拒绝发布")
        void publishObsoleteRejected() {
            Document doc = buildSavedDoc();
            doc.setStatus(DocumentStatus.OBSOLETE);
            when(documentRepository.findById(1L)).thenReturn(Optional.of(doc));

            IllegalStateException ex = assertThrows(IllegalStateException.class, () ->
                    documentService.publish(1L, "test", adminUser, "pwd", "meaning"));
            assertTrue(ex.getMessage().contains("已作废"));
        }

        @Test
        @DisplayName("REVIEW 状态拒绝发布")
        void publishReviewRejected() {
            Document doc = buildSavedDoc();
            doc.setStatus(DocumentStatus.REVIEW);
            when(documentRepository.findById(1L)).thenReturn(Optional.of(doc));

            IllegalStateException ex = assertThrows(IllegalStateException.class, () ->
                    documentService.publish(1L, "test", adminUser, "pwd", "meaning"));
            assertTrue(ex.getMessage().contains("审核中"));
        }

        @Test
        @DisplayName("无权限（非ADMIN非上传人）拒绝发布")
        void publishNoPermissionRejected() {
            Document doc = buildSavedDoc();
            doc.setStatus(DocumentStatus.DRAFT);
            doc.setUploader(adminUser);
            when(documentRepository.findById(1L)).thenReturn(Optional.of(doc));

            assertThrows(SecurityException.class, () ->
                    documentService.publish(1L, "test", normalUser, "pwd", "meaning"));
        }

        @Test
        @DisplayName("文档不存在拒绝发布")
        void publishDocNotFound() {
            when(documentRepository.findById(999L)).thenReturn(Optional.empty());

            assertThrows(IllegalArgumentException.class, () ->
                    documentService.publish(999L, "test", adminUser, "pwd", "meaning"));
        }

        @Test
        @DisplayName("DocumentFile 不存在拒绝发布")
        void publishFileMissing() {
            Document doc = buildSavedDoc();
            doc.setStatus(DocumentStatus.DRAFT);
            when(documentRepository.findById(1L)).thenReturn(Optional.of(doc));
            when(fileRepository.findByDocumentId(1L)).thenReturn(Optional.empty());

            assertThrows(IllegalStateException.class, () ->
                    documentService.publish(1L, "test", adminUser, "pwd", "meaning"));
        }
    }

    // ============ Workflow Tests (审批工作流) ============

    @Nested
    @DisplayName("审批工作流: submitForReview / approve / reject / retire")
    class WorkflowTests {

        @Test
        @DisplayName("1. submitForReview: DRAFT -> REVIEW（上传人提交）")
        void submitForReviewSuccess() {
            Document doc = buildSavedDoc();
            doc.setStatus(DocumentStatus.DRAFT);
            doc.setUploader(normalUser);
            when(documentRepository.findById(1L)).thenReturn(Optional.of(doc));
            when(documentRepository.save(any(Document.class))).thenAnswer(inv -> inv.getArgument(0));

            DocumentDetailDto result = documentService.submitForReview(1L, normalUser);

            assertEquals("REVIEW", result.getStatus());
            verify(documentRepository).save(any(Document.class));
        }

        @Test
        @DisplayName("2. submitForReview: ADMIN 也可提交")
        void adminCanSubmitForReview() {
            Document doc = buildSavedDoc();
            doc.setStatus(DocumentStatus.DRAFT);
            when(documentRepository.findById(1L)).thenReturn(Optional.of(doc));
            when(documentRepository.save(any(Document.class))).thenAnswer(inv -> inv.getArgument(0));

            DocumentDetailDto result = documentService.submitForReview(1L, adminUser);

            assertEquals("REVIEW", result.getStatus());
        }

        @Test
        @DisplayName("3. submitForReview: 非 DRAFT 状态拒绝")
        void submitForReviewNonDraftRejected() {
            Document doc = buildSavedDoc();
            doc.setStatus(DocumentStatus.PUBLISHED);
            when(documentRepository.findById(1L)).thenReturn(Optional.of(doc));

            IllegalStateException ex = assertThrows(IllegalStateException.class, () ->
                    documentService.submitForReview(1L, adminUser));
            assertTrue(ex.getMessage().contains("仅草稿状态可提交评审"));
        }

        @Test
        @DisplayName("4. submitForReview: 无权限（非ADMIN非上传人）拒绝")
        void submitForReviewNoPermissionRejected() {
            Document doc = buildSavedDoc();
            doc.setStatus(DocumentStatus.DRAFT);
            doc.setUploader(adminUser);
            when(documentRepository.findById(1L)).thenReturn(Optional.of(doc));

            assertThrows(SecurityException.class, () ->
                    documentService.submitForReview(1L, normalUser));
        }

        @Test
        @DisplayName("5. approve: REVIEW -> PUBLISHED v1.0（首次审批通过）")
        void approveFirstTimeSuccess() {
            Document doc = buildSavedDoc();
            doc.setStatus(DocumentStatus.REVIEW);
            doc.setVersion(null);
            DocumentFile docFile = new DocumentFile(1L, "content".getBytes(), "abc123");

            when(documentRepository.findById(1L)).thenReturn(Optional.of(doc));
            when(fileRepository.findByDocumentId(1L)).thenReturn(Optional.of(docFile));
            when(documentRepository.save(any(Document.class))).thenAnswer(inv -> inv.getArgument(0));
            // 签名服务 mock（电子签名通过）
            when(signatureService.verifyAndRecord(any(), any(), any(), any(), any(), any()))
                    .thenReturn(new SignatureRecord());

            DocumentDetailDto result = documentService.approve(1L, "内容合规", adminUser, "pwd", "meaning");

            assertEquals("PUBLISHED", result.getStatus());
            assertEquals("v1.0", result.getVersion());
            // 应创建一条 APPROVED 审批记录
            verify(reviewRepository).save(any(DocumentReview.class));
            // 应创建一条 Revision 快照
            verify(revisionRepository).save(any(DocumentRevision.class));
        }

        @Test
        @DisplayName("6. approve: 非 ADMIN 拒绝")
        void approveNonAdminRejected() {
            Document doc = buildSavedDoc();
            doc.setStatus(DocumentStatus.REVIEW);
            when(documentRepository.findById(1L)).thenReturn(Optional.of(doc));

            assertThrows(SecurityException.class, () ->
                    documentService.approve(1L, "ok", normalUser, "pwd", "meaning"));
        }

        @Test
        @DisplayName("7. approve: 非 REVIEW 状态拒绝")
        void approveNonReviewRejected() {
            Document doc = buildSavedDoc();
            doc.setStatus(DocumentStatus.DRAFT);
            when(documentRepository.findById(1L)).thenReturn(Optional.of(doc));

            IllegalStateException ex = assertThrows(IllegalStateException.class, () ->
                    documentService.approve(1L, "ok", adminUser, "pwd", "meaning"));
            assertTrue(ex.getMessage().contains("仅审核中状态可审批"));
        }

        @Test
        @DisplayName("8. reject: REVIEW -> DRAFT（驳回）")
        void rejectSuccess() {
            Document doc = buildSavedDoc();
            doc.setStatus(DocumentStatus.REVIEW);
            when(documentRepository.findById(1L)).thenReturn(Optional.of(doc));
            when(documentRepository.save(any(Document.class))).thenAnswer(inv -> inv.getArgument(0));
            // 签名服务 mock
            when(signatureService.verifyAndRecord(any(), any(), any(), any(), any(), any()))
                    .thenReturn(new SignatureRecord());

            DocumentDetailDto result = documentService.reject(1L, "格式不符规范", adminUser, "pwd", "meaning");

            assertEquals("DRAFT", result.getStatus());
            // 应创建一条 REJECTED 审批记录
            verify(reviewRepository).save(any(DocumentReview.class));
            // 不应创建 Revision（被驳回，不发布）
            verify(revisionRepository, never()).save(any(DocumentRevision.class));
        }

        @Test
        @DisplayName("9. reject: 无 comment 拒绝（驳回必须给理由）")
        void rejectWithoutCommentRejected() {
            Document doc = buildSavedDoc();
            doc.setStatus(DocumentStatus.REVIEW);
            when(documentRepository.findById(1L)).thenReturn(Optional.of(doc));

            assertThrows(IllegalArgumentException.class, () ->
                    documentService.reject(1L, "", adminUser, "pwd", "meaning"));
            assertThrows(IllegalArgumentException.class, () ->
                    documentService.reject(1L, null, adminUser, "pwd", "meaning"));
        }

        @Test
        @DisplayName("10. reject: 非 ADMIN 拒绝")
        void rejectNonAdminRejected() {
            Document doc = buildSavedDoc();
            doc.setStatus(DocumentStatus.REVIEW);
            when(documentRepository.findById(1L)).thenReturn(Optional.of(doc));

            assertThrows(SecurityException.class, () ->
                    documentService.reject(1L, "reason", normalUser, "pwd", "meaning"));
        }

        @Test
        @DisplayName("11. retire: PUBLISHED -> OBSOLETE")
        void retireSuccess() {
            Document doc = buildSavedDoc();
            doc.setStatus(DocumentStatus.PUBLISHED);
            when(documentRepository.findById(1L)).thenReturn(Optional.of(doc));
            when(documentRepository.save(any(Document.class))).thenAnswer(inv -> inv.getArgument(0));
            // 签名服务 mock
            when(signatureService.verifyAndRecord(any(), any(), any(), any(), any(), any()))
                    .thenReturn(new SignatureRecord());

            DocumentDetailDto result = documentService.retire(1L, adminUser, "pwd", "meaning");

            assertEquals("OBSOLETE", result.getStatus());
            assertNotNull(result.getObsoleteDate());
        }

        @Test
        @DisplayName("12. retire: 非 PUBLISHED 状态拒绝")
        void retireNonPublishedRejected() {
            Document doc = buildSavedDoc();
            doc.setStatus(DocumentStatus.DRAFT);
            when(documentRepository.findById(1L)).thenReturn(Optional.of(doc));

            IllegalStateException ex = assertThrows(IllegalStateException.class, () ->
                    documentService.retire(1L, adminUser, "pwd", "meaning"));
            assertTrue(ex.getMessage().contains("仅已发布状态可作废"));
        }

        @Test
        @DisplayName("13. retire: 非 ADMIN 拒绝")
        void retireNonAdminRejected() {
            Document doc = buildSavedDoc();
            doc.setStatus(DocumentStatus.PUBLISHED);
            when(documentRepository.findById(1L)).thenReturn(Optional.of(doc));

            assertThrows(SecurityException.class, () ->
                    documentService.retire(1L, normalUser, "pwd", "meaning"));
        }

        @Test
        @DisplayName("14. 完整审批流: submit -> reject -> resubmit -> approve -> retire")
        void completeWorkflowWithRejection() {
            // Phase 1: submit
            Document doc = buildSavedDoc();
            doc.setStatus(DocumentStatus.DRAFT);
            doc.setVersion(null);
            doc.setUploader(normalUser);
            DocumentFile docFile = new DocumentFile(1L, "content".getBytes(), "abc123");

            when(documentRepository.findById(1L)).thenReturn(Optional.of(doc));
            when(fileRepository.findByDocumentId(1L)).thenReturn(Optional.of(docFile));
            when(documentRepository.save(any(Document.class))).thenAnswer(inv -> {
                Document d = inv.getArgument(0);
                return d;
            });
            // 签名服务 mock（reject/approve/retire 都会调用）
            when(signatureService.verifyAndRecord(any(), any(), any(), any(), any(), any()))
                    .thenReturn(new SignatureRecord());

            DocumentDetailDto r1 = documentService.submitForReview(1L, normalUser);
            assertEquals("REVIEW", r1.getStatus());

            // Phase 2: reject -> DRAFT
            doc.setStatus(DocumentStatus.REVIEW);
            DocumentDetailDto r2 = documentService.reject(1L, "需要补充信息", adminUser, "pwd", "meaning");
            assertEquals("DRAFT", r2.getStatus());

            // Phase 3: resubmit -> REVIEW
            doc.setStatus(DocumentStatus.DRAFT);
            DocumentDetailDto r3 = documentService.submitForReview(1L, normalUser);
            assertEquals("REVIEW", r3.getStatus());

            // Phase 4: approve -> PUBLISHED v1.0
            doc.setStatus(DocumentStatus.REVIEW);
            DocumentDetailDto r4 = documentService.approve(1L, "已补充", adminUser, "pwd", "meaning");
            assertEquals("PUBLISHED", r4.getStatus());
            assertEquals("v1.0", r4.getVersion());

            // Phase 5: retire -> OBSOLETE
            doc.setStatus(DocumentStatus.PUBLISHED);
            doc.setVersion("v1.0");
            DocumentDetailDto r5 = documentService.retire(1L, adminUser, "pwd", "meaning");
            assertEquals("OBSOLETE", r5.getStatus());

            // 验证审批记录创建: 1 reject + 1 approve = 2 次
            verify(reviewRepository, times(2)).save(any(DocumentReview.class));
        }

        @Test
        @DisplayName("15. listReviews: 返回审批历史 DTO")
        void listReviewsReturnsDtos() {
            Document doc = buildSavedDoc();
            doc.setStatus(DocumentStatus.PUBLISHED);
            adminUser.setRealName("系统管理员");
            when(documentRepository.findById(1L)).thenReturn(Optional.of(doc));
            when(userRepository.findById(1L)).thenReturn(Optional.of(adminUser));

            DocumentReview r1 = new DocumentReview(1L, 1L, ReviewDecision.APPROVED, "通过", "v1.0");
            r1.setId(10L);
            when(reviewRepository.findByDocumentIdOrderByReviewedAtDesc(1L))
                    .thenReturn(List.of(r1));

            var result = documentService.listReviews(1L, adminUser);

            assertEquals(1, result.size());
            assertEquals("系统管理员", result.get(0).getReviewerName());
            assertEquals(ReviewDecision.APPROVED, result.get(0).getDecision());
            assertEquals("v1.0", result.get(0).getVersionAfter());
        }
    }

    // ============ ListRevisions Tests ============

    @Nested
    @DisplayName("listRevisions() 修订历史")
    class ListRevisionsTests {

        @Test
        @DisplayName("正常返回修订列表")
        void listRevisionsSuccess() {
            Document doc = buildSavedDoc();
            doc.setVisibility(DocumentVisibility.PUBLIC);
            when(documentRepository.findById(1L)).thenReturn(Optional.of(doc));

            DocumentRevision rev1 = new DocumentRevision();
            rev1.setId(1L);
            rev1.setDocumentId(1L);
            rev1.setVersion("v1.0");
            rev1.setTitle("v1.0 标题");
            rev1.setFileName("test.pdf");
            rev1.setFileSize(100L);
            rev1.setPublishedById(1L);
            rev1.setPublishedAt(LocalDateTime.now());

            when(revisionRepository.findByDocumentIdOrderByPublishedAtDesc(1L))
                    .thenReturn(List.of(rev1));

            List<DocumentRevisionDto> result = documentService.listRevisions(1L, normalUser);

            assertEquals(1, result.size());
            assertEquals("v1.0", result.get(0).getVersion());
        }

        @Test
        @DisplayName("文档不存在拒绝")
        void listRevisionsDocNotFound() {
            when(documentRepository.findById(999L)).thenReturn(Optional.empty());

            assertThrows(IllegalArgumentException.class, () ->
                    documentService.listRevisions(999L, adminUser));
        }

        @Test
        @DisplayName("无权限拒绝")
        void listRevisionsNoPermission() {
            Document doc = buildSavedDoc();
            doc.setVisibility(DocumentVisibility.DEPARTMENT);
            doc.setDepartment(dept1);
            when(documentRepository.findById(1L)).thenReturn(Optional.of(doc));

            assertThrows(SecurityException.class, () ->
                    documentService.listRevisions(1L, normalUser));
        }
    }

    // ============ Diff Tests ============

    @Nested
    @DisplayName("diff() 版本对比")
    class DiffTests {

        @Test
        @DisplayName("元数据变更检测")
        void diffMetadataChanges() {
            Document doc = buildSavedDoc();
            doc.setVisibility(DocumentVisibility.PUBLIC);
            when(documentRepository.findById(1L)).thenReturn(Optional.of(doc));

            DocumentRevision fromRev = new DocumentRevision();
            fromRev.setId(1L);
            fromRev.setDocumentId(1L);
            fromRev.setVersion("v1.0");
            fromRev.setTitle("旧标题");
            fromRev.setDescription("旧描述");
            fromRev.setFileName("test.pdf");
            fromRev.setFileSize(100L);
            fromRev.setFileType("application/pdf");
            fromRev.setFileExtension("pdf");
            fromRev.setChecksum("abc");

            DocumentRevision toRev = new DocumentRevision();
            toRev.setId(2L);
            toRev.setDocumentId(1L);
            toRev.setVersion("v1.1");
            toRev.setTitle("新标题");
            toRev.setDescription("旧描述");
            toRev.setFileName("test.pdf");
            toRev.setFileSize(100L);
            toRev.setFileType("application/pdf");
            toRev.setFileExtension("pdf");
            toRev.setChecksum("abc");

            when(revisionRepository.findById(1L)).thenReturn(Optional.of(fromRev));
            when(revisionRepository.findById(2L)).thenReturn(Optional.of(toRev));

            DocumentDiffDto result = documentService.diff(1L, 1L, 2L, normalUser);

            assertEquals("v1.0", result.getFromVersion());
            assertEquals("v1.1", result.getToVersion());
            assertFalse(result.isContentChanged());
            assertTrue(result.getChanges().stream().anyMatch(c -> c.getField().equals("title")));
        }

        @Test
        @DisplayName("checksum 不同 -> contentChanged=true")
        void diffContentChanged() {
            Document doc = buildSavedDoc();
            doc.setVisibility(DocumentVisibility.PUBLIC);
            when(documentRepository.findById(1L)).thenReturn(Optional.of(doc));

            DocumentRevision fromRev = buildRevision(1L, "v1.0", "title", "abc");
            DocumentRevision toRev = buildRevision(2L, "v1.1", "title", "def");

            when(revisionRepository.findById(1L)).thenReturn(Optional.of(fromRev));
            when(revisionRepository.findById(2L)).thenReturn(Optional.of(toRev));

            DocumentDiffDto result = documentService.diff(1L, 1L, 2L, normalUser);

            assertTrue(result.isContentChanged());
        }

        @Test
        @DisplayName("from==to -> 空 changes")
        void diffSameRevision() {
            Document doc = buildSavedDoc();
            doc.setVisibility(DocumentVisibility.PUBLIC);
            when(documentRepository.findById(1L)).thenReturn(Optional.of(doc));

            DocumentRevision rev = buildRevision(1L, "v1.0", "title", "abc");

            when(revisionRepository.findById(1L)).thenReturn(Optional.of(rev));

            DocumentDiffDto result = documentService.diff(1L, 1L, 1L, normalUser);

            assertTrue(result.getChanges().isEmpty());
            assertFalse(result.isContentChanged());
        }

        @Test
        @DisplayName("Revision 不属于该文档拒绝")
        void diffRevisionMismatch() {
            Document doc = buildSavedDoc();
            doc.setVisibility(DocumentVisibility.PUBLIC);
            when(documentRepository.findById(1L)).thenReturn(Optional.of(doc));

            DocumentRevision wrongRev = buildRevision(1L, "v1.0", "title", "abc");
            wrongRev.setDocumentId(999L);  // 不属于文档 1

            when(revisionRepository.findById(1L)).thenReturn(Optional.of(wrongRev));

            assertThrows(IllegalArgumentException.class, () ->
                    documentService.diff(1L, 1L, 1L, normalUser));
        }
    }

    // ============ Rollback Tests ============

    @Nested
    @DisplayName("rollback() 回滚")
    class RollbackTests {

        @Test
        @DisplayName("非 ADMIN 拒绝回滚")
        void rollbackNonAdminRejected() {
            assertThrows(SecurityException.class, () ->
                    documentService.rollback(1L, 1L, normalUser, "pwd", "meaning"));
        }

        @Test
        @DisplayName("文档不存在拒绝")
        void rollbackDocNotFound() {
            when(documentRepository.findById(999L)).thenReturn(Optional.empty());

            assertThrows(IllegalArgumentException.class, () ->
                    documentService.rollback(999L, 1L, adminUser, "pwd", "meaning"));
        }

        @Test
        @DisplayName("目标 Revision 不存在拒绝")
        void rollbackRevNotFound() {
            Document doc = buildSavedDoc();
            when(documentRepository.findById(1L)).thenReturn(Optional.of(doc));
            when(revisionRepository.findById(999L)).thenReturn(Optional.empty());

            assertThrows(IllegalArgumentException.class, () ->
                    documentService.rollback(1L, 999L, adminUser, "pwd", "meaning"));
        }

        @Test
        @DisplayName("目标为当前版本拒绝（无意义）")
        void rollbackCurrentVersionRejected() {
            Document doc = buildSavedDoc();
            doc.setVersion("v1.0");
            DocumentRevision targetRev = buildRevision(1L, "v1.0", "title", "abc");
            targetRev.setDocumentId(1L);

            when(documentRepository.findById(1L)).thenReturn(Optional.of(doc));
            when(revisionRepository.findById(1L)).thenReturn(Optional.of(targetRev));

            assertThrows(IllegalStateException.class, () ->
                    documentService.rollback(1L, 1L, adminUser, "pwd", "meaning"));
        }

        @Test
        @DisplayName("正常回滚创建新版本")
        void rollbackSuccess() {
            Document doc = buildSavedDoc();
            doc.setVersion("v1.1");
            doc.setStatus(DocumentStatus.PUBLISHED);
            doc.setTitle("v1.1 标题");

            DocumentRevision targetRev = buildRevision(5L, "v1.0", "v1.0 标题", "old-checksum");
            targetRev.setDocumentId(1L);
            targetRev.setDescription("v1.0 描述");
            targetRev.setFileName("old.pdf");
            targetRev.setFileSize(200L);
            targetRev.setFileType("application/pdf");
            targetRev.setFileExtension("pdf");
            targetRev.setContentSnapshot("old-content".getBytes());

            DocumentFile currentFile = new DocumentFile(1L, "new-content".getBytes(), "new-checksum");
            DocumentRevision lastRev = buildRevision(10L, "v1.1", "v1.1 标题", "new-checksum");

            when(documentRepository.findById(1L)).thenReturn(Optional.of(doc));
            when(revisionRepository.findById(5L)).thenReturn(Optional.of(targetRev));
            when(fileRepository.findByDocumentId(1L)).thenReturn(Optional.of(currentFile));
            when(revisionRepository.findTopByDocumentIdOrderByPublishedAtDesc(1L))
                    .thenReturn(Optional.of(lastRev));
            when(revisionRepository.findById(10L)).thenReturn(Optional.of(lastRev));
            when(documentRepository.save(any(Document.class))).thenAnswer(inv -> inv.getArgument(0));
            // 签名服务 mock
            when(signatureService.verifyAndRecord(any(), any(), any(), any(), any(), any()))
                    .thenReturn(new SignatureRecord());

            DocumentDetailDto result = documentService.rollback(1L, 5L, adminUser, "pwd", "meaning");

            assertEquals("v1.2", result.getVersion());
            assertEquals("PUBLISHED", result.getStatus());
            // 验证 Document 元数据已被覆盖为目标版本
            assertEquals("v1.0 标题", result.getTitle());
            // 验证快照保存（回滚前快照 + 标记前序作废）
            verify(revisionRepository, atLeastOnce()).save(any(DocumentRevision.class));
            // 验证 DocumentFile 内容已被覆盖
            verify(fileRepository).save(any(DocumentFile.class));
        }
    }

    // ============ RESEARCH 可见性回归测试（Phase 5 新增，规则更新：同部门全见 + 跨部门授权） ============

    @Nested
    @DisplayName("RESEARCH 资料可见性 - 统一规则 + SHARED 策略")
    class ResearchVisibilityTests {

        @Test
        @DisplayName("同部门员工（非负责人）可访问本部门他人 TOP_SECRET 研发资料")
        void sameDeptMemberCanAccessTopSecretInSameDept() {
            Document doc = buildResearchDoc();
            doc.setConfidentialityLevel(ConfidentialityLevel.TOP_SECRET);
            // deptMember（非 leader，dept1）访问 leaderUser（dept1）的 TOP_SECRET 资料
            doc.setOwner(leaderUser);
            when(documentRepository.findById(1L)).thenReturn(Optional.of(doc));

            assertDoesNotThrow(() -> documentService.getResearchMaterialDetail(1L, deptMember));
        }

        @Test
        @DisplayName("allowedLevels 授权用户可访问对应等级他人研发资料（跨部门授权场景）")
        void allowedLevelsUserCanAccessAuthorizedLevel() {
            Document doc = buildResearchDoc();
            doc.setConfidentialityLevel(ConfidentialityLevel.CONFIDENTIAL);
            doc.setOwner(deptMember);  // dept1 owner
            when(documentRepository.findById(1L)).thenReturn(Optional.of(doc));
            // normalUser（dept2，跨部门）被授权 CONFIDENTIAL 等级
            when(dataVisibilityChecker.getAllowedLevels(normalUser))
                    .thenReturn(Set.of(ConfidentialityLevel.CONFIDENTIAL));

            assertDoesNotThrow(() -> documentService.getResearchMaterialDetail(1L, normalUser));
        }

        @Test
        @DisplayName("跨部门员工无授权不可访问他人 INTERNAL 研发资料（需 allowedLevels 授权）")
        void crossDeptUserCannotAccessOthersInternalWithoutGrant() {
            Document doc = buildResearchDoc();
            doc.setConfidentialityLevel(ConfidentialityLevel.INTERNAL);
            doc.setOwner(deptMember);  // dept1 owner
            when(documentRepository.findById(1L)).thenReturn(Optional.of(doc));
            // normalUser 在 dept2，跨部门无授权
            when(shareRepository.existsByDocumentIdAndSharedWithUserId(1L, normalUser.getId()))
                    .thenReturn(false);

            SecurityException ex = assertThrows(SecurityException.class, () ->
                    documentService.getResearchMaterialDetail(1L, normalUser));
            assertTrue(ex.getMessage().contains("无权访问该研发资料"));
        }

        @Test
        @DisplayName("category grant 释放跨部门非 TOP_SECRET 研发资料")
        void categoryGrantReleasesCrossDeptNonTopSecret() {
            Document doc = buildResearchDoc();
            doc.setConfidentialityLevel(ConfidentialityLevel.INTERNAL);
            doc.setOwner(deptMember);  // dept1
            doc.setCategory(category);  // category.id = 1
            when(documentRepository.findById(1L)).thenReturn(Optional.of(doc));
            // normalUser（dept2，跨部门）无 allowedLevels，但有 category grant
            when(dataVisibilityChecker.getAllowedLevels(normalUser)).thenReturn(Set.of());
            when(dataVisibilityChecker.getAllowedCategoryIds(normalUser)).thenReturn(Set.of(1L));

            assertDoesNotThrow(() -> documentService.getResearchMaterialDetail(1L, normalUser));
        }

        @Test
        @DisplayName("TOP_SECRET 不被 category grant 释放（即使有 category grant 也不可见）")
        void topSecretNotReleasedByCategoryGrant() {
            Document doc = buildResearchDoc();
            doc.setConfidentialityLevel(ConfidentialityLevel.TOP_SECRET);
            doc.setOwner(deptMember);  // dept1
            doc.setCategory(category);  // category.id = 1
            when(documentRepository.findById(1L)).thenReturn(Optional.of(doc));
            when(dataVisibilityChecker.getAllowedLevels(normalUser)).thenReturn(Set.of());
            when(dataVisibilityChecker.getAllowedCategoryIds(normalUser)).thenReturn(Set.of(1L));

            SecurityException ex = assertThrows(SecurityException.class, () ->
                    documentService.getResearchMaterialDetail(1L, normalUser));
            assertTrue(ex.getMessage().contains("绝密等级"));
        }

        @Test
        @DisplayName("无 category 字段（category=null）走默认规则（category grant 不命中）")
        void nullCategoryFallsThroughToDefault() {
            Document doc = buildResearchDoc();
            doc.setConfidentialityLevel(ConfidentialityLevel.INTERNAL);
            doc.setOwner(deptMember);  // dept1
            doc.setCategory(null);  // 无分类
            when(documentRepository.findById(1L)).thenReturn(Optional.of(doc));
            when(dataVisibilityChecker.getAllowedLevels(normalUser)).thenReturn(Set.of());
            when(dataVisibilityChecker.getAllowedCategoryIds(normalUser)).thenReturn(Set.of(1L));
            when(shareRepository.existsByDocumentIdAndSharedWithUserId(1L, normalUser.getId()))
                    .thenReturn(false);

            SecurityException ex = assertThrows(SecurityException.class, () ->
                    documentService.getResearchMaterialDetail(1L, normalUser));
            assertTrue(ex.getMessage().contains("无权访问该研发资料"));
        }
    }

    // ============ Helper ============

    private Document buildSavedDoc() {
        Document doc = new Document();
        doc.setId(1L);
        doc.setTitle("测试文档");
        doc.setFileName("test.pdf");
        doc.setFileSize(100L);
        doc.setFileType("application/pdf");
        doc.setFileExtension("pdf");
        doc.setVisibility(DocumentVisibility.PUBLIC);
        doc.setCategory(category);
        doc.setUploader(adminUser);
        return doc;
    }

    /** 构建测试用 RESEARCH 类型文档（研发资料） */
    private Document buildResearchDoc() {
        Document doc = new Document();
        doc.setId(1L);
        doc.setTitle("研发资料测试");
        doc.setFileName("research.pdf");
        doc.setFileSize(100L);
        doc.setFileType("application/pdf");
        doc.setFileExtension("pdf");
        doc.setDocType(DocumentType.RESEARCH);
        doc.setVisibility(DocumentVisibility.ASSIGNEES);
        doc.setConfidentialityLevel(ConfidentialityLevel.INTERNAL);
        doc.setCategory(category);
        doc.setUploader(adminUser);
        return doc;
    }

    /** 构建测试用 DocumentRevision 快照 */
    private DocumentRevision buildRevision(Long id, String version, String title, String checksum) {
        DocumentRevision rev = new DocumentRevision();
        rev.setId(id);
        rev.setDocumentId(1L);
        rev.setVersion(version);
        rev.setTitle(title);
        rev.setDescription("描述");
        rev.setFileName("test.pdf");
        rev.setFileSize(100L);
        rev.setFileType("application/pdf");
        rev.setFileExtension("pdf");
        rev.setChecksum(checksum);
        rev.setContentSnapshot("content".getBytes());
        rev.setPublishedById(1L);
        rev.setPublishedAt(LocalDateTime.now());
        return rev;
    }
}
