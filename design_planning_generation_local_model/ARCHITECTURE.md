# QMS 医疗器械文档生成 Agent - 架构文档

## 1. 项目概述

### 1.1 目标
为医疗器械企业构建一个 AI Agent，能够根据用户需求自动生成符合法规的质量体系文档（QMS），输出为 Word 格式。

### 1.2 使用场景
质量体系部门员工需要完成各类质量体系文件的编写，通过本工具，只需指定文档类型和产品信息，即可自动生成完整的文档。

### 1.3 核心流程

```
用户输入（文档类型 + 产品信息） → AI 生成内容 → Word 文档输出
```

### 1.4 技术栈

| 组件 | 选型 | 说明 |
|------|------|------|
| Web 前端 | HTML + JavaScript | 简单表单界面 |
| 后端框架 | FastAPI | 轻量、自动化文档、类型安全 |
| AI API | MiniMax API | 用户已有配置 |
| Word 库 | python-docx | 纯 Python，支持 .docx 格式 |
| 模板来源 | 复用现有模板 | 来自 develop_documents/ |

---

## 2. 系统架构

### 2.1 整体架构图

```
┌─────────────────────────────────────────────────────────────┐
│                      Web Browser                             │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐  │
│  │  文档类型    │    │  产品信息    │    │  下载按钮    │  │
│  │  下拉选择    │    │  文本输入    │    │              │  │
│  └──────┬───────┘    └──────┬───────┘    └──────▲───────┘  │
│         │                   │                   │           │
│         └───────────────────┼───────────────────┘           │
│                             │ POST /api/generate            │
└─────────────────────────────┼───────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      FastAPI Backend                         │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                  /api/generate                       │   │
│  │  1. Validate input (doc_type, product_info)          │   │
│  │  2. Select template by doc_type                      │   │
│  │  3. Build prompt with template + product_info        │   │
│  │  4. Call MiniMax API                                 │   │
│  │  5. Fill Word template with response                 │   │
│  │  6. Return .docx file                               │   │
│  └─────────────────────────────────────────────────────┘   │
│                              │                              │
│              ┌───────────────┼───────────────┐              │
│              ▼               ▼               ▼              │
│  ┌─────────────────┐ ┌─────────────┐ ┌──────────────┐      │
│  │ Template Loader  │ │ MiniMax API │ │ Word Filler  │      │
│  │                 │ │  Connector  │ │              │      │
│  └────────┬────────┘ └──────┬──────┘ └──────┬───────┘      │
│           │                 │               │               │
└───────────┼─────────────────┼───────────────┼───────────────┘
            │                 │               │
            ▼                 ▼               ▼
    ┌──────────────┐  ┌─────────────┐  ┌──────────────┐
    │  .docx 模板  │  │ MiniMax API │  │ python-docx │
    │  文件夹      │  │             │  │ 库          │
    └──────────────┘  └─────────────┘  └──────────────┘
```

### 2.2 目录结构

```
qms_agent/
├── app/
│   ├── main.py              # FastAPI 入口
│   ├── api/
│   │   └── routes.py        # API 路由
│   ├── services/
│   │   ├── generator.py     # 文档生成逻辑
│   │   ├── minimax.py       # MiniMax API 调用
│   │   └── template.py      # 模板加载/填充
│   ├── templates/           # Word 模板
│   │   ├── risk_management/ # 风险管理报告模板
│   │   ├── product_spec/     # 产品技术要求模板
│   │   ├── instruction/      # 说明书模板
│   │   └── sop/              # SOP 作业指导书模板
│   └── static/
│       └── index.html       # Web 前端页面
├── requirements.txt
└── run.py                   # 启动脚本
```

---

## 3. API 设计

### 3.1 生成文档接口

```
POST /api/generate
Content-Type: application/json
```

**请求参数：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| doc_type | string | 是 | 文档类型 |
| product_name | string | 是 | 产品名称 |
| product_type | string | 是 | 产品类型（如：有源医疗器械） |
| product_params | string | 否 | 产品参数详情 |

**doc_type 可选值：**

| 值 | 说明 | 对应模板 |
|----|------|----------|
| risk_management | 风险管理报告 | 风险管理报告模板 |
| product_spec | 产品技术要求 | 产品技术要求模板 |
| instruction | 使用说明书 | 说明书模板 |
| sop | 作业指导书 | SOP 模板 |

**请求示例：**

```json
{
  "doc_type": "risk_management",
  "product_name": "胰岛素泵",
  "product_type": "有源医疗器械",
  "product_params": "闭环控制，Bluetooth LE 通讯，0.05U基础输注精度"
}
```

**响应：**

- 成功：Word 文件 (.docx) 二进制流
- 失败：

```json
{
  "error": "错误信息描述"
}
```

### 3.2 健康检查接口

```
GET /api/health
```

**响应：**

```json
{
  "status": "ok"
}
```

---

## 4. 核心模块设计

### 4.1 Template Service (template.py)

**职责：** 管理 Word 模板的加载和内容填充

**关键函数：**

```python
def load_template(doc_type: str) -> Document:
    """根据文档类型加载对应模板"""

def fill_template(doc: Document, content: dict) -> Document:
    """用 AI 生成的内容填充模板"""
```

**模板映射表：**

| doc_type | 模板目录 |
|----------|----------|
| risk_management | templates/risk_management/ |
| product_spec | templates/product_spec/ |
| instruction | templates/instruction/ |
| sop | templates/sop/ |

### 4.2 MiniMax Service (minimax.py)

**职责：** 调用 MiniMax API 生成文档内容

**关键函数：**

```python
def generate_content(doc_type: str, product_info: dict) -> str:
    """调用 AI API 生成文档内容"""

def build_prompt(doc_type: str, product_info: dict) -> str:
    """构建 AI prompt，包含模板指引和法规要求"""
```

**Prompt 构建策略：**
- 根据 doc_type 加载对应的法规标准要求
- 注入产品信息作为上下文
- 指定输出格式（Markdown 或结构化文本）

### 4.3 Generator Service (generator.py)

**职责：** 协调整个生成流程

**关键函数：**

```python
async def generate_document(request: GenerateRequest) -> bytes:
    """
    1. 验证输入参数
    2. 加载模板
    3. 调用 AI 生成内容
    4. 填充模板
    5. 返回 Word 文件字节
    """
```

### 4.4 主入口 (main.py)

```python
from fastapi import FastAPI
from app.api.routes import router

app = FastAPI(title="QMS Document Generator")
app.include_router(router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

---

## 5. 数据流

```
用户输入
    │
    ▼
┌─────────────┐
│ 参数验证    │
└──────┬──────┘
       │
       ▼
┌─────────────┐    ┌─────────────┐
│ 选择模板    │◀───│ 获取文档类型│
└──────┬──────┘    └─────────────┘
       │
       ▼
┌─────────────┐
│ 构建 Prompt │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ 调用 AI API │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ 填充模板    │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ 返回文件    │
└─────────────┘
```

---

## 6. 前端页面

### 6.1 页面布局

```
┌─────────────────────────────────────────┐
│           QMS 文档生成工具               │
├─────────────────────────────────────────┤
│                                         │
│  文档类型：                             │
│  [▼ 风险管理报告    ]                    │
│                                         │
│  产品名称：                             │
│  [___________________]                  │
│                                         │
│  产品类型：                             │
│  [▼ 有源医疗器械  ]                      │
│                                         │
│  产品参数：                             │
│  ┌─────────────────────────────────┐   │
│  │                                 │   │
│  │                                 │   │
│  └─────────────────────────────────┘   │
│                                         │
│         [ 开始生成 ]                     │
│                                         │
│  状态：待输入                            │
│                                         │
└─────────────────────────────────────────┘
```

### 6.2 交互流程

1. 用户选择文档类型
2. 用户填写产品信息
3. 点击"开始生成"
4. 显示加载状态
5. 生成完成后自动下载文件

---

## 7. 模板来源与整理

### 7.1 现有模板

来自 `develop_documents/` 目录，包含 66+ 个 Word 模板：

| 类别 | 数量 | 内容 |
|------|------|------|
| CH3.2 风险管理模板 | ~15 | 风险管理报告、风险评估表 |
| 产品技术要求模板 | ~20 | 技术要求、注册资料模板 |
| CH5.03 包装说明使用说明书 | ~6 | 说明书范本 |
| 软件资料 | ~10 | IEC 62304 相关文档 |
| 其他 | ~15 | 流程图、验证报告、SOP |

### 7.2 模板整理计划

Phase 1 中需要手动整理模板到 `app/templates/` 目录：

```
app/templates/
├── risk_management/
│   ├── 风险管理报告模板.docx
│   └── 风险评估表.docx
├── product_spec/
│   ├── 产品技术要求模板.docx
│   └── 标准列表模板.docx
├── instruction/
│   └── 说明书模板.docx
└── sop/
    └── 作业指导书模板.docx
```

---

## 8. 实施计划

### Phase 1：MVP（当前阶段）

- [x] 架构设计
- [ ] 项目初始化
- [ ] 模板整理
- [ ] API 实现
- [ ] 前端页面
- [ ] 联调测试

### Phase 2（后续）

- [ ] 文档审查/优化功能
- [ ] 多文档批量生成
- [ ] 用户认证系统

---

## 9. 风险与应对

| 风险 | 影响 | 应对措施 |
|------|------|----------|
| MiniMax API 响应格式不稳定 | 生成内容解析失败 | 增加响应校验和解析容错 |
| 部分模板是旧 .doc 格式 | 无法用 python-docx 处理 | 仅使用 .docx 格式模板 |
| Word 内容超长 | API 或处理超时 | 分块处理，设置超时限制 |

---

## 10. 测试计划

### 单元测试

```python
# tests/test_generator.py
def test_validate_input_valid():
    """有效输入应该通过验证"""

def test_validate_input_invalid_doc_type():
    """无效 doc_type 应该抛出异常"""

def test_generate_content_success():
    """正常调用应该返回内容"""
```

### 集成测试

```python
# tests/test_api.py
def test_generate_endpoint_success():
    """完整生成流程应该返回 Word 文件"""

def test_generate_endpoint_invalid_params():
    """无效参数应该返回错误"""
```

---

## 11. 启动方式

```bash
# 安装依赖
pip install -r requirements.txt

# 启动服务
python run.py
# 或
uvicorn app.main:app --reload --port 8000

# 访问页面
http://localhost:8000
```
