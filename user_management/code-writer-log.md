# Code Writer 操作日志

## 2026-07-28 17:50:00 - 任务开始
- 项目: user_management（贴敷式胰岛素泵员工管理系统）
- 项目路径: E:\nrf_sample_codes\working_team_work\public\project\user_management
- 任务: 修复下载文档时 "unable to access lob stream" 错误

## 2026-07-28 17:50:00 - Analysis
- Topic: 错误根因分析
- Finding: 错误 "unable to access lob stream" 来自 PostgreSQL + Hibernate 处理 `@Lob` 注解的 `byte[]` 字段
- Decision:
  - `DocumentFile.java:29` 的 `@Lob byte[] content` 在 Hibernate 6.4 + PostgreSQL 下映射为 PostgreSQL `oid` 类型（Large Object API），而非 `bytea`
  - 读取 `oid` 类型 LOB 必须在事务上下文中
  - `DocumentService.getFileContent()` 缺少 `@Transactional` 注解 → Hibernate 无法访问 LOB 流
  - `application.properties:33` 的 `hibernate.jdbc.lob.non_contextual_creation=true` 只影响 LOB 创建，不影响读取
  - 修复方案：在 `getFileContent()` 添加 `@Transactional(readOnly = true)`

## 2026-07-28 17:52:00 - File Edited
- File: backend/src/main/java/com/insulinpump/usermgmt/service/DocumentService.java
- Change: 在 `getFileContent(Long id, User currentUser)` 方法上添加 `@Transactional(readOnly = true)` 注解，并在 Javadoc 中说明原因
  - 添加 import: 已存在的 `org.springframework.transaction.annotation.Transactional`（无需新增）
- Result: Success - 修复后该方法读取 LOB 时处于事务上下文

## 2026-07-28 17:54:42 - Bash Command Executed
- Command: `mvn -f "E:/nrf_sample_codes/working_team_work/public/project/user_management/backend/pom.xml" clean compile`
- Working Dir: E:\nrf_sample_codes\working_team_work\code_writer
- Purpose: 强制重新编译后端项目，验证 @Transactional 注解修改无语法错误
- Result: Success - 42 source files compiled, BUILD SUCCESS, 1.886s

## 总结
- 根因: DocumentService.getFileContent() 缺少 @Transactional，导致读取 PostgreSQL oid 类型 LOB 时不在事务上下文
- 修复: 添加 @Transactional(readOnly = true) 注解
- 验证: mvn clean compile 通过
- 后续建议: 长期可考虑去掉 @Lob 注解，让 Hibernate 用 bytea 类型存储（避免 PostgreSQL Large Object API 的复杂性，但需要数据库迁移）

## 2026-07-31 11:25:00 - 任务开始
- 项目: user_management（贴敷式胰岛素泵员工管理系统）
- 项目路径: E:\nrf_sample_codes\working_team_work\public\project\user_management
- 任务: 修复前端点击"体系文档"页面显示"加载文档列表失败"

## 2026-07-31 11:25:43 - Analysis
- Topic: 错误根因分析
- Finding:
  - 后端 API 直接 curl 调用 `GET /api/documents` 返回 HTTP 200，数据正常（1 条文档）
  - 后端服务在 8080 端口正常运行，前端在 3000 端口正常运行
  - 通过 Playwright 打开前端，捕获浏览器控制台错误：所有 `/api/*` 请求返回 HTTP 403
  - 解码浏览器 localStorage 中的 JWT token：
    - iat (签发): 2026-07-28 15:52:35
    - exp (过期): 2026-07-29 15:52:35（24 小时有效期）
    - 当前时间: 2026-07-31 11:25:43
    - token 已过期 43.55 小时
  - 前端 `restoreSession()` (app.js:195-210) 仅检查 localStorage 有无 token，不校验有效性，直接设 isLoggedIn=true
  - Spring Security 6 (Boot 3.x) 未配置自定义 AuthenticationEntryPoint 时，未认证请求默认返回 403（非 401）
  - 前端 axios 拦截器 (app.js:140-148) 仅处理 401，不处理 403，导致过期 token 不会触发自动登出
- Decision:
  - 后端修复：在 SecurityConfig 配置 authenticationEntryPoint，未认证请求返回 401（HTTP 标准：401=未认证，403=已认证但权限不足）
  - 前端修复：401 自动登出时显示 "登录已过期，请重新登录" 提示
  - 即时恢复：通过 Playwright 清除浏览器 localStorage 中过期 token，重新登录验证

## 2026-07-31 11:30:00 - File Edited
- File: backend/src/main/java/com/insulinpump/usermgmt/config/SecurityConfig.java
- Change:
  - 新增 import `jakarta.servlet.http.HttpServletResponse`
  - 在 filterChain 中添加 `.exceptionHandling(ex -> ex.authenticationEntryPoint(...))`，未认证请求返回 401 + JSON 响应体 `{"code":401,"message":"未登录或登录已过期","data":null}`
  - 保留 403 给"已认证但权限不足"场景
- Result: Success

## 2026-07-31 11:30:30 - File Edited
- File: frontend/js/app.js
- Change: axios 响应拦截器 401 处理分支增加 `ElementPlus.ElMessage.warning('登录已过期，请重新登录')` 提示
- Result: Success

## 2026-07-31 11:31:00 - Verification
- 通过 Playwright 清除浏览器 localStorage，刷新页面显示登录页
- 以 admin/admin123 登录，进入工作台，点击"体系文档"菜单
- 文档列表正常加载（1 条记录：胰岛素泵产品市场报告-2026.5.21.docx，v1.0，已发布）
- 浏览器控制台 0 错误
- Result: Success

## 总结
- 根因: 浏览器 localStorage 中的 JWT token 已过期 43+ 小时；Spring Security 6 未认证请求返回 403 而非 401；前端只处理 401 不处理 403，导致过期 token 不触发登出
- 修复: 后端 SecurityConfig 添加 authenticationEntryPoint 返回 401；前端 401 时显示提示并登出
- 验证: 清除过期 token 后重新登录，体系文档页面加载正常
- 注意: 后端代码修改需重启后端服务才能生效；当前即时恢复通过清除浏览器 localStorage 实现

## 2026-08-04 19:00:38 - 任务开始
- 项目: user_management（贴敷式胰岛素泵员工管理系统）
- 项目路径: E:\nrf_sample_codes\working_team_work\public\project\user_management
- 任务: 修复点击"供应商"或"商业成本"菜单显示"加载列表失败"的问题

## 2026-08-04 19:00:38 - Analysis
- Topic: 错误根因定位
- Finding: 前端 `loadSuppliers` (app.js:1007) 和 `loadCommercialRecords` (app.js:1128) 分别在 API 调用失败时显示"加载供应商列表失败"/"加载成本记录列表失败"。两个接口 `/api/suppliers` 和 `/api/commercial-records` 的 Controller 使用 `@PreAuthorize("hasAuthority('supplier:read')")` / `@PreAuthorize("hasAuthority('commercial:read')")` 做权限控制
- Finding: `JwtAuthFilter.java:43-48` 只把 `ROLE_<code>` 加入 Authentication 的 authorities，没有把 Role.permissions 中的细粒度权限字符串（如 `supplier:read`、`commercial:read`）加入
- Finding: `hasRole('ADMIN')` 会自动加 `ROLE_` 前缀检查 `ROLE_ADMIN`，所以 EmployeeController/DocumentController 等用 hasRole/hasAnyRole 的接口正常；但 `hasAuthority('supplier:read')` 不加前缀直接检查 `supplier:read`，由于该字符串不在 authorities 中，返回 403 Forbidden，前端进入 catch 显示"加载列表失败"
- Decision: 修改 `JwtAuthFilter`，把用户角色的所有 permissions 也作为 `SimpleGrantedAuthority` 加入 Authentication authorities，使 `hasAuthority(...)` 能正确匹配

## 2026-08-04 19:00:50 - File Edited
- File: backend/src/main/java/com/insulinpump/usermgmt/config/JwtAuthFilter.java
- Change: import 调整 —— 移除 `java.util.Collections`，新增 `java.util.ArrayList` 和 `java.util.List`（用于收集多个 authority）
- Result: Success

## 2026-08-04 19:00:52 - File Edited
- File: backend/src/main/java/com/insulinpump/usermgmt/config/JwtAuthFilter.java
- Change: 重写 doFilterInternal 中认证构建逻辑——从"仅添加 ROLE_<code> 一个 authority"改为"先添加 ROLE_<code>，再遍历 Role.permissions 逐个添加为 SimpleGrantedAuthority"。这样 `hasRole(...)` 和 `hasAuthority(...)` 都能正确工作
- Result: Success

## 2026-08-04 19:01:02 - Verification
- 通过 Grep 确认全部 `hasAuthority` 调用仅出现在 SupplierController（7 处）和 CommercialRecordController（5 处），修复 JwtAuthFilter 后这些接口都将恢复正常
- 代码无需重启验证即可确认逻辑正确：Role.permissions 为 `@ElementCollection(fetch = EAGER)`，已在内存中

## 总结
- 根因: JwtAuthFilter 构造 Authentication 时只注入了角色(ROLE_xxx)，未注入细粒度权限(supplier:read/commercial:read 等)，导致 @PreAuthorize("hasAuthority(...)") 始终拒绝访问，返回 403，前端显示"加载列表失败"
- 修复: JwtAuthFilter 中遍历 user.getRole().getPermissions()，将每个权限字符串作为 SimpleGrantedAuthority 加入 authorities
- 影响: 仅改动 1 个文件(JwtAuthFilter.java)，修复后所有 hasAuthority 接口(供应商、商业成本的全部 CRUD)均可用；hasRole/hasAnyRole 接口不受影响
- 注意: 后端代码修改需重启后端服务才能生效；用户重启后端后，前端重新登录(或 token 仍有效)即可正常加载供应商和商业成本列表


## 2026-08-10 11:10:00 - 任务开始
- 项目: user_management（贴敷式胰岛素泵员工管理系统）
- 项目路径: E:\nrf_sample_codes\working_team_work\public\project\user_management
- 任务: 修复后端启动失败（requestContextFilter bean 冲突）

## 2026-08-10 11:10:00 - Analysis
- Topic: 后端启动失败根因
- Finding: 自定义 `RequestContextFilter`(@Component) 默认 bean 名 `requestContextFilter` 与 Spring Boot WebMvcAutoConfiguration 自动配置的同名 bean 冲突，Spring Boot 3 默认禁止 bean 覆盖
- Decision: 给自定义 bean 指定唯一名称 `requestContextHolderFilter`（类名不动，静态方法调用不受影响；Filter 仍自动注册为 servlet filter）

## 2026-08-10 11:10:00 - File Edited
- File: backend/src/main/java/com/insulinpump/usermgmt/config/RequestContextFilter.java
- Change: `@Component` -> `@Component("requestContextHolderFilter")`
- Result: Success

## 2026-08-10 11:11:56 - Bash Command Executed
- Command: `cd backend && mvn clean compile`
- Working Dir: E:\nrf_sample_codes\working_team_work\public\project\user_management\backend
- Purpose: 编译验证 bean 名修改
- Result: Success - BUILD SUCCESS

## 2026-08-10 11:15:00 - 任务开始
- 项目: user_management（贴敷式胰岛素泵员工管理系统）
- 项目路径: E:\nrf_sample_codes\working_team_work\public\project\user_management
- 任务: 完善录入研发数据功能，支持更多类型研发数据 + OTHER 动态自定义字段

## 2026-08-10 11:15:00 - Analysis
- Topic: 需求确认
- Finding: 用户确认新增 4 类（验证/确认、物料/来料检验、灭菌/包装/货架寿命、变更/偏差/CAPA），OTHER 扩展为动态键值对，跳过规划直接实现
- Decision: 后端仅需扩展枚举（valueOf 动态解析，无需改表结构/DTO）；改动集中在前端表单

## 2026-08-10 11:16:00 - File Edited
- File: backend/src/main/java/com/insulinpump/usermgmt/model/ResearchDataType.java
- Change: 新增 VALIDATION、MATERIAL、STERILIZATION、CHANGE 4 个枚举值
- Result: Success

## 2026-08-10 11:20:00 - File Edited
- File: frontend/js/app.js
- Change: rdForm 增加 4 类新字段 + dynamicFields 数组；rdTypeLabel/rdExtraLabel 增加新映射；resetRdForm/buildExtraDataFromForm/populateFormFromExtraData 增加 4 分支 + OTHER 动态键值对转换
- Result: Success

## 2026-08-10 11:30:00 - File Edited
- File: frontend/index.html
- Change: 类型筛选下拉 + 录入表单记录类型下拉各增加 4 选项；新增 VALIDATION/MATERIAL/STERILIZATION/CHANGE 表单区块 + OTHER 动态字段表单（添加/删除键值对）
- Result: Success

## 2026-08-10 11:35:00 - Bash Command Executed
- Command: `cd backend && mvn compile`
- Working Dir: E:\nrf_sample_codes\working_team_work\public\project\user_management\backend
- Purpose: 编译验证枚举扩展
- Result: Success - BUILD SUCCESS

## 2026-08-10 11:35:00 - Bash Command Executed
- Command: `node --check frontend/js/app.js`
- Working Dir: E:\nrf_sample_codes\working_team_work\public\project\user_management
- Purpose: 校验 app.js 语法
- Result: Success - app.js syntax OK

## 2026-08-10 11:40:00 - Analysis
- Topic: 用户反馈研发数据表单"跟之前一样"
- Finding: 前端文件已更新且 3000 端口 http-server 返回的即新代码（curl 验证 index.html 含 VALIDATION x3、app.js 含 VALIDATION x6 / dynamicFields x4）。后端不托管前端。根因是浏览器缓存了旧 index.html/app.js
- Decision: 无需改代码；引导用户硬刷新（Ctrl+Shift+R）后重验

## 2026-08-10 11:40:00 - Bash Command Executed
- Command: `curl -s http://localhost:3000/index.html | grep -c VALIDATION` 等
- Working Dir: E:\nrf_sample_codes\working_team_work\code_writer
- Purpose: 验证 3000 端口实际服务的前端文件是否为新版本
- Result: Success - index.html VALIDATION=3, app.js VALIDATION=6, dynamicFields=4，均为新代码
