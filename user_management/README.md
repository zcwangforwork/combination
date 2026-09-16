# 贴敷式胰岛素泵员工管理系统

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端 | Spring Boot 3.2.5 + Spring Security + JWT + JPA |
| 前端 | Vue.js 3 + Element Plus (CDN, 零构建) |
| 数据库 | PostgreSQL |
| 认证 | JWT (jjwt 0.12.5) |

## 项目结构

```
user_management/
├── backend/                          # Spring Boot 后端
│   ├── pom.xml
│   └── src/main/java/com/insulinpump/usermgmt/
│       ├── UserManagementApplication.java
│       ├── config/                   # SecurityConfig, JWT, CORS, DataInit
│       ├── controller/               # REST API 控制器
│       ├── dto/                      # 数据传输对象
│       ├── exception/                # 全局异常处理
│       ├── model/                    # JPA 实体 (User, Role, Department)
│       ├── repository/               # Spring Data JPA 仓库
│       └── service/                  # 业务逻辑层
└── frontend/                         # Vue.js 3 前端 (CDN 方式)
    ├── index.html                    # 单页应用入口
    ├── css/style.css
    └── js/app.js                     # Vue 应用逻辑
```

## 启动步骤

### 1. 创建 PostgreSQL 数据库

```sql
CREATE DATABASE user_management WITH ENCODING 'UTF8';
```

### 2. 修改数据库配置

编辑 `backend/src/main/resources/application.properties`，修改数据库连接信息：

```properties
spring.datasource.url=jdbc:postgresql://localhost:5432/user_management
spring.datasource.username=postgres
spring.datasource.password=your_password
```

### 3. 启动后端

```bash
cd backend
mvn spring-boot:run
```

后端启动在 `http://localhost:8080`

### 4. 启动前端

方式一：用任意 HTTP 服务器（推荐）
```bash
cd frontend
npx http-server -p 3000 --cors
```

方式二：直接用浏览器打开 `frontend/index.html`（需浏览器允许跨域）

### 5. 登录

| 用户名 | 密码 | 角色 |
|--------|------|------|
| admin | admin123 | 系统管理员 |
| zhangsan | 123456 | 结构工程师 |
| lisi | 123456 | 电路工程师 |
| wangwu | 123456 | 测试工程师 |
| zhaoliu | 123456 | 体系工程师 |
| sunqi | 123456 | 质量工程师 |
| zhouba | 123456 | 注册工程师 |
| wujiu | 123456 | 软件工程师 |
| zhengshi | 123456 | 生产工程师 |

## API 接口

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| POST | /api/auth/login | 用户登录 | 公开 |
| POST | /api/auth/register | 用户注册 | 公开 |
| GET | /api/auth/me | 获取当前用户信息 | 登录用户 |
| GET | /api/employees | 员工列表(分页) | 登录用户 |
| GET | /api/employees/{id} | 员工详情 | 登录用户 |
| POST | /api/employees | 添加员工 | 管理员 |
| PUT | /api/employees/{id} | 更新员工 | 管理员 |
| DELETE | /api/employees/{id} | 删除员工 | 管理员 |
| GET | /api/roles | 角色列表 | 登录用户 |
| GET | /api/departments | 部门列表 | 登录用户 |
| GET | /api/dashboard/stats | 仪表盘统计 | 登录用户 |

## 角色权限

| 角色 | 编码 | 权限 |
|------|------|------|
| 系统管理员 | ADMIN | 全部权限 (employee:read/write/delete) |
| 结构工程师 | STRUCTURAL_ENGINEER | 查看员工、查看仪表盘 |
| 电路工程师 | CIRCUIT_ENGINEER | 查看员工、查看仪表盘 |
| 测试工程师 | TEST_ENGINEER | 查看员工、查看仪表盘 |
| 体系工程师 | SYSTEM_ENGINEER | 查看员工、查看仪表盘 |
| 质量工程师 | QUALITY_ENGINEER | 查看员工、查看仪表盘 |
| 注册工程师 | REGULATORY_ENGINEER | 查看员工、查看仪表盘 |
| 软件工程师 | SOFTWARE_ENGINEER | 查看员工、查看仪表盘 |
| 生产工程师 | PRODUCTION_ENGINEER | 查看员工、查看仪表盘 |

## JWT 密钥

默认密钥在 `application.properties` 中的 `app.jwt.secret`，**生产环境请务必更换**。
Token 有效期默认 24 小时（`app.jwt.expiration-ms=86400000`）。
