package com.insulinpump.usermgmt.controller;

import com.insulinpump.usermgmt.dto.ApiResponse;
import com.insulinpump.usermgmt.dto.CommercialRecordDetailDto;
import com.insulinpump.usermgmt.dto.CommercialRecordListDto;
import com.insulinpump.usermgmt.dto.CommercialRecordRequest;
import com.insulinpump.usermgmt.model.User;
import com.insulinpump.usermgmt.service.CommercialRecordService;
import org.springframework.data.domain.Page;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

/**
 * 商业成本记录 Controller
 *
 * 权限矩阵（同 ResearchData，owner+ADMIN 模式）：
 *  - GET    /api/commercial-records           登录用户（受可见性约束：owner/ADMIN/PUBLIC）
 *  - GET    /api/commercial-records/{id}      登录用户（受可见性约束）
 *  - POST   /api/commercial-records           登录用户
 *  - PUT    /api/commercial-records/{id}      owner 或 ADMIN
 *  - DELETE /api/commercial-records/{id}      owner 或 ADMIN
 *
 * 默认保密等级：CONFIDENTIAL（成本价是敏感商业数据）
 */
@RestController
@RequestMapping("/api/commercial-records")
public class CommercialRecordController {

    private final CommercialRecordService commercialRecordService;

    public CommercialRecordController(CommercialRecordService commercialRecordService) {
        this.commercialRecordService = commercialRecordService;
    }

    /**
     * 商业成本记录列表
     *
     * @param view "mine"=我的 / "all"=全部(仅ADMIN) / "public"=全员可见 / 其他=mine∪public
     */
    @GetMapping
    @PreAuthorize("hasAuthority('commercial:read')")
    public ResponseEntity<ApiResponse<Page<CommercialRecordListDto>>> list(
            @AuthenticationPrincipal User currentUser,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size,
            @RequestParam(required = false) Long supplierId,
            @RequestParam(required = false) String keyword,
            @RequestParam(required = false) String confidentialityLevel,
            @RequestParam(required = false) String view) {
        Page<CommercialRecordListDto> result = commercialRecordService.list(
                page, size, supplierId, keyword, confidentialityLevel, view, currentUser);
        return ResponseEntity.ok(ApiResponse.success(result));
    }

    @GetMapping("/{id}")
    @PreAuthorize("hasAuthority('commercial:read')")
    public ResponseEntity<ApiResponse<CommercialRecordDetailDto>> getById(
            @PathVariable Long id,
            @AuthenticationPrincipal User currentUser) {
        return ResponseEntity.ok(ApiResponse.success(
                commercialRecordService.getById(id, currentUser)));
    }

    @PostMapping
    @PreAuthorize("hasAuthority('commercial:write')")
    public ResponseEntity<ApiResponse<CommercialRecordDetailDto>> create(
            @RequestBody CommercialRecordRequest req,
            @AuthenticationPrincipal User currentUser) {
        return ResponseEntity.ok(ApiResponse.success("创建成功",
                commercialRecordService.create(req, currentUser)));
    }

    @PutMapping("/{id}")
    @PreAuthorize("hasAuthority('commercial:write')")
    public ResponseEntity<ApiResponse<CommercialRecordDetailDto>> update(
            @PathVariable Long id,
            @RequestBody CommercialRecordRequest req,
            @AuthenticationPrincipal User currentUser) {
        return ResponseEntity.ok(ApiResponse.success("更新成功",
                commercialRecordService.update(id, req, currentUser)));
    }

    @DeleteMapping("/{id}")
    @PreAuthorize("hasAuthority('commercial:delete')")
    public ResponseEntity<ApiResponse<Void>> delete(
            @PathVariable Long id,
            @AuthenticationPrincipal User currentUser) {
        commercialRecordService.delete(id, currentUser);
        return ResponseEntity.ok(ApiResponse.success("删除成功", null));
    }
}
