package com.insulinpump.usermgmt.controller;

import com.insulinpump.usermgmt.dto.ApiResponse;
import com.insulinpump.usermgmt.dto.SupplierDetailDto;
import com.insulinpump.usermgmt.dto.SupplierListDto;
import com.insulinpump.usermgmt.dto.SupplierRequest;
import com.insulinpump.usermgmt.model.User;
import com.insulinpump.usermgmt.service.SupplierService;
import org.springframework.data.domain.Page;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

import java.util.List;

/**
 * 供应商 Controller（主数据风格）
 *
 * 权限矩阵：
 *  - GET    /api/suppliers           登录用户（含停用记录，主数据全可见）
 *  - GET    /api/suppliers/{id}      登录用户
 *  - GET    /api/suppliers/enabled   登录用户（下拉选择用，仅启用）
 *  - POST   /api/suppliers           仅 ADMIN
 *  - PUT    /api/suppliers/{id}      仅 ADMIN
 *  - DELETE /api/suppliers/{id}      仅 ADMIN（软删除 enabled=false）
 *  - PUT    /api/suppliers/{id}/enable  仅 ADMIN（恢复已停用）
 *
 * 软删除策略：enabled=false 保留 FK 引用（CommercialRecord 历史保留供应商名）。
 */
@RestController
@RequestMapping("/api/suppliers")
public class SupplierController {

    private final SupplierService supplierService;

    public SupplierController(SupplierService supplierService) {
        this.supplierService = supplierService;
    }

    /**
     * 供应商列表
     *
     * @param includeDisabled 是否包含已停用记录（默认 true：主数据风格，历史供应商需可见）
     */
    @GetMapping
    @PreAuthorize("hasAuthority('supplier:read')")
    public ResponseEntity<ApiResponse<Page<SupplierListDto>>> list(
            @AuthenticationPrincipal User currentUser,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size,
            @RequestParam(required = false) String category,
            @RequestParam(required = false) String qualificationStatus,
            @RequestParam(required = false) String keyword,
            @RequestParam(required = false) Boolean includeDisabled) {
        Page<SupplierListDto> result = supplierService.list(
                page, size, category, qualificationStatus, keyword,
                includeDisabled != null ? includeDisabled : true, currentUser);
        return ResponseEntity.ok(ApiResponse.success(result));
    }

    /**
     * 启用中的供应商列表（下拉选择用，按名称排序）
     */
    @GetMapping("/enabled")
    @PreAuthorize("hasAuthority('supplier:read')")
    public ResponseEntity<ApiResponse<List<SupplierListDto>>> listEnabled() {
        return ResponseEntity.ok(ApiResponse.success(supplierService.listEnabled()));
    }

    @GetMapping("/{id}")
    @PreAuthorize("hasAuthority('supplier:read')")
    public ResponseEntity<ApiResponse<SupplierDetailDto>> getById(@PathVariable Long id) {
        return ResponseEntity.ok(ApiResponse.success(supplierService.getById(id)));
    }

    @PostMapping
    @PreAuthorize("hasAuthority('supplier:write')")
    public ResponseEntity<ApiResponse<SupplierDetailDto>> create(
            @RequestBody SupplierRequest req,
            @AuthenticationPrincipal User currentUser) {
        return ResponseEntity.ok(ApiResponse.success("创建成功",
                supplierService.create(req, currentUser)));
    }

    @PutMapping("/{id}")
    @PreAuthorize("hasAuthority('supplier:write')")
    public ResponseEntity<ApiResponse<SupplierDetailDto>> update(
            @PathVariable Long id,
            @RequestBody SupplierRequest req,
            @AuthenticationPrincipal User currentUser) {
        return ResponseEntity.ok(ApiResponse.success("更新成功",
                supplierService.update(id, req, currentUser)));
    }

    /**
     * 软删除（停用）供应商
     */
    @DeleteMapping("/{id}")
    @PreAuthorize("hasAuthority('supplier:delete')")
    public ResponseEntity<ApiResponse<Void>> delete(
            @PathVariable Long id,
            @AuthenticationPrincipal User currentUser) {
        supplierService.disable(id, currentUser);
        return ResponseEntity.ok(ApiResponse.success("已停用", null));
    }

    /**
     * 恢复已停用的供应商
     */
    @PutMapping("/{id}/enable")
    @PreAuthorize("hasAuthority('supplier:write')")
    public ResponseEntity<ApiResponse<Void>> enable(
            @PathVariable Long id,
            @AuthenticationPrincipal User currentUser) {
        supplierService.enable(id, currentUser);
        return ResponseEntity.ok(ApiResponse.success("已启用", null));
    }
}
