package com.insulinpump.usermgmt.controller;

import com.insulinpump.usermgmt.dto.ApiResponse;
import com.insulinpump.usermgmt.dto.ResearchDataDetailDto;
import com.insulinpump.usermgmt.dto.ResearchDataListDto;
import com.insulinpump.usermgmt.dto.ResearchDataRequest;
import com.insulinpump.usermgmt.model.User;
import com.insulinpump.usermgmt.service.ResearchDataService;
import org.springframework.data.domain.Page;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

/**
 * 研发数据 Controller（结构化记录，区别于 ResearchMaterialController 的文件上传）
 *
 * 用户通过前端表格直接录入研发过程数据（测试记录/设计参数/实验记录/故障记录），
 * 数据直接存入数据库（非文件），类型相关字段通过 extraData JSONB 存储。
 *
 * 权限矩阵：
 *  - GET    /api/research-data           登录用户（受可见性约束：owner/ADMIN/PUBLIC）
 *  - GET    /api/research-data/{id}      登录用户（受可见性约束）
 *  - POST   /api/research-data           登录用户
 *  - PUT    /api/research-data/{id}      owner 或 ADMIN
 *  - DELETE /api/research-data/{id}      owner 或 ADMIN
 */
@RestController
@RequestMapping("/api/research-data")
public class ResearchDataController {

    private final ResearchDataService researchDataService;

    public ResearchDataController(ResearchDataService researchDataService) {
        this.researchDataService = researchDataService;
    }

    /**
     * 研发数据列表
     *
     * @param view "mine"=我的 / "all"=全部(仅ADMIN) / "public"=全员可见 / 其他=mine∪public
     */
    @GetMapping
    public ResponseEntity<ApiResponse<Page<ResearchDataListDto>>> list(
            @AuthenticationPrincipal User currentUser,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size,
            @RequestParam(required = false) String recordType,
            @RequestParam(required = false) Long categoryId,
            @RequestParam(required = false) String keyword,
            @RequestParam(required = false) String confidentialityLevel,
            @RequestParam(required = false) String paramCategory,
            @RequestParam(required = false) String view) {
        Page<ResearchDataListDto> result = researchDataService.list(
                page, size, recordType, categoryId, keyword, confidentialityLevel,
                paramCategory, view, currentUser);
        return ResponseEntity.ok(ApiResponse.success(result));
    }

    /**
     * 研发数据详情
     */
    @GetMapping("/{id}")
    public ResponseEntity<ApiResponse<ResearchDataDetailDto>> getById(
            @PathVariable Long id,
            @AuthenticationPrincipal User currentUser) {
        ResearchDataDetailDto dto = researchDataService.getById(id, currentUser);
        return ResponseEntity.ok(ApiResponse.success(dto));
    }

    /**
     * 创建研发数据
     */
    @PostMapping
    public ResponseEntity<ApiResponse<ResearchDataDetailDto>> create(
            @RequestBody ResearchDataRequest req,
            @AuthenticationPrincipal User currentUser) {
        ResearchDataDetailDto dto = researchDataService.create(req, currentUser);
        return ResponseEntity.ok(ApiResponse.success("创建成功", dto));
    }

    /**
     * 更新研发数据（部分更新）
     */
    @PutMapping("/{id}")
    public ResponseEntity<ApiResponse<ResearchDataDetailDto>> update(
            @PathVariable Long id,
            @RequestBody ResearchDataRequest req,
            @AuthenticationPrincipal User currentUser) {
        ResearchDataDetailDto dto = researchDataService.update(id, req, currentUser);
        return ResponseEntity.ok(ApiResponse.success("更新成功", dto));
    }

    /**
     * 删除研发数据
     */
    @DeleteMapping("/{id}")
    public ResponseEntity<ApiResponse<Void>> delete(
            @PathVariable Long id,
            @AuthenticationPrincipal User currentUser) {
        researchDataService.delete(id, currentUser);
        return ResponseEntity.ok(ApiResponse.success("删除成功", null));
    }
}
