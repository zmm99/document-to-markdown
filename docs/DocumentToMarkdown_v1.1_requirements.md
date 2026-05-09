# DocumentToMarkdown v1.1 需求文档

## 1. 版本目标

v1.1 在 v1.0 文档转换能力基础上，升级为带异步任务、文件管理、任务管理和简单管理页面的内网文档转换服务。

本版本重点解决：

- 其他系统可以通过开放 API 上传文件并异步解析。
- 其他系统可以查询任务状态和进度。
- 其他系统可以获取文档信息、Markdown、附件和完整 zip 结果。
- 管理人员可以通过 `/web` 页面登录后管理文件和任务。
- 管理人员可以删除解析缓存，也可以彻底删除文件。

## 2. 使用角色

### 2.1 外部系统

外部系统通过开放 API 集成 DocumentToMarkdown。

外部系统需要：

- 上传文件并发起解析。
- 查询解析任务状态和进度。
- 在解析成功后获取 Markdown。
- 获取图片附件。
- 下载完整解析结果 zip。

外部系统不需要：

- 删除缓存。
- 删除文件。
- 取消任务。
- 重试任务。
- 查看全局文件列表或任务列表。

### 2.2 管理人员

管理人员通过 `/web` 管理页面使用系统。

管理人员需要：

- 登录管理页面。
- 上传文件并查看解析进度。
- 查看文件列表。
- 查看任务列表。
- 查询文件和任务。
- 查看文件详情。
- 预览 Markdown。
- 获取附件和下载 zip。
- 删除解析缓存。
- 删除文件。
- 重试失败任务。
- 取消等待中或运行中的任务。
- 删除任务记录。

## 3. 接口访问边界

### 3.1 开放 API

开放 API 不要求登录，不做鉴权保护。

开放 API 用于其他系统集成，必须保持稳定、简单、可轮询。

开放 API 包括：

```http
POST /api/documents/convert
POST /api/tasks/convert
GET  /api/tasks/{task_id}
GET  /api/documents/{file_id}
GET  /api/documents/{file_id}/markdown
GET  /api/documents/{file_id}/assets/{asset_name}
GET  /api/documents/{file_id}/download
```

说明：

- `POST /api/documents/convert` 为 v1.0 同步转换接口，v1.1 继续保留。
- `POST /api/tasks/convert` 为 v1.1 新增异步转换接口。
- `GET /api/tasks/{task_id}` 必须返回任务状态和进度。
- 文档结果读取接口保持开放，便于外部系统下载结果。
- 开放 API 暂不支持删除、重试、取消和列表能力。

### 3.2 管理 API

管理 API 要求登录后访问。

管理 API 包括：

```http
GET    /api/tasks
POST   /api/tasks/{task_id}/retry
POST   /api/tasks/{task_id}/cancel
DELETE /api/tasks/{task_id}

GET    /api/documents
POST   /api/documents/{file_id}/reconvert
DELETE /api/documents/{file_id}/cache
DELETE /api/documents/{file_id}

POST   /api/auth/logout
GET    /api/auth/me
```

说明：

- `POST /api/auth/login` 不要求已登录。
- `/web` 管理页面要求登录。
- 删除类、重试类、列表类接口只对管理页面开放。

## 4. 登录需求

v1.1 实现简单登录，不实现多用户体系。

账号密码来自 `.env`：

```env
ADMIN_USERNAME=admin
ADMIN_PASSWORD=change-me
SESSION_SECRET=change-me-too
SESSION_EXPIRE_HOURS=12
```

登录要求：

- 管理页面 `/web` 未登录时跳转登录页。
- 管理 API 未登录时返回 401。
- 登录成功后使用 HTTP-only cookie 保存会话。
- 退出登录后清除 cookie。

不要求：

- 用户注册。
- 用户表。
- 角色权限。
- 密码修改。
- 多管理员。

## 5. 异步任务需求

### 5.1 创建任务

外部系统或管理页面通过以下接口创建异步转换任务：

```http
POST /api/tasks/convert
Content-Type: multipart/form-data
```

请求字段：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| file | file | 是 | 待转换文件 |

成功响应：

```json
{
  "task_id": "311234567890123456",
  "file_id": "311234567890123000",
  "status": "queued",
  "progress": {
    "percent": 20,
    "stage": "queued",
    "message": "waiting for conversion"
  },
  "status_url": "/api/tasks/311234567890123456",
  "document_url": "/api/documents/311234567890123000"
}
```

### 5.2 查询任务状态

外部系统通过以下接口轮询任务状态：

```http
GET /api/tasks/{task_id}
```

任务处理中响应：

```json
{
  "task_id": "311234567890123456",
  "file_id": "311234567890123000",
  "status": "running",
  "file_format": "pdf",
  "progress": {
    "percent": 40,
    "stage": "converting",
    "message": "converting document"
  },
  "result": null
}
```

任务成功响应：

```json
{
  "task_id": "311234567890123456",
  "file_id": "311234567890123000",
  "status": "success",
  "file_format": "pdf",
  "progress": {
    "percent": 100,
    "stage": "success",
    "message": "conversion completed"
  },
  "result": {
    "file_id": "311234567890123000",
    "markdown_url": "/api/documents/311234567890123000/markdown",
    "download_url": "/api/documents/311234567890123000/download",
    "assets": []
  }
}
```

任务失败响应：

```json
{
  "task_id": "311234567890123456",
  "file_id": "311234567890123000",
  "status": "failed",
  "file_format": "pdf",
  "progress": {
    "percent": 100,
    "stage": "failed",
    "message": "conversion failed"
  },
  "error_code": "convert_failed",
  "message": "document conversion failed",
  "result": null
}
```

## 6. 任务状态和进度

任务状态：

| 状态 | 说明 |
| --- | --- |
| `queued` | 已入队，等待执行 |
| `running` | 正在执行 |
| `success` | 执行成功 |
| `failed` | 执行失败 |
| `timeout` | 执行超时 |
| `cancelled` | 已取消 |

进度字段：

```json
{
  "percent": 40,
  "stage": "converting",
  "message": "converting document"
}
```

进度阶段：

| 阶段 | percent | stage | message |
| --- | ---: | --- | --- |
| 创建任务 | 0 | `created` | `task created` |
| 上传完成 | 10 | `uploaded` | `file uploaded` |
| 已入队 | 20 | `queued` | `waiting for conversion` |
| 开始转换 | 40 | `converting` | `converting document` |
| 写入结果 | 80 | `writing_result` | `writing conversion result` |
| 保存记录 | 90 | `saving_record` | `saving conversion record` |
| 成功 | 100 | `success` | `conversion completed` |
| 失败 | 100 | `failed` | `conversion failed` |
| 超时 | 100 | `timeout` | `conversion timed out` |
| 取消 | 100 | `cancelled` | `task cancelled` |

说明：

- v1.1 进度采用阶段进度，不要求页级精确进度。
- 外部系统只需要根据 `status` 和 `progress.percent` 判断任务状态。
- 后续版本可以接入转换器内部进度。

## 7. 文件管理需求

### 7.1 开放读取能力

以下接口保持开放：

```http
GET /api/documents/{file_id}
GET /api/documents/{file_id}/markdown
GET /api/documents/{file_id}/assets/{asset_name}
GET /api/documents/{file_id}/download
```

### 7.2 管理能力

以下接口要求登录：

```http
GET    /api/documents
POST   /api/documents/{file_id}/reconvert
DELETE /api/documents/{file_id}/cache
DELETE /api/documents/{file_id}
```

文件列表支持查询条件：

| 参数 | 说明 |
| --- | --- |
| `keyword` | 按原始文件名模糊搜索 |
| `file_format` | 按文件格式筛选 |
| `status` | 按最近转换状态筛选 |
| `date_from` | 上传开始日期 |
| `date_to` | 上传结束日期 |
| `page` | 页码 |
| `page_size` | 每页数量 |

删除要求：

- 删除缓存：删除解析记录、附件记录和输出目录，保留原始上传文件。
- 删除文件：删除原始上传文件、解析记录、附件记录和输出目录。
- 删除文件必须只在管理 API 中提供。

## 8. 任务管理需求

任务列表要求登录：

```http
GET /api/tasks
```

任务列表支持查询条件：

| 参数 | 说明 |
| --- | --- |
| `keyword` | 按原始文件名模糊搜索 |
| `file_format` | 按文件格式筛选 |
| `status` | 按任务状态筛选 |
| `date_from` | 创建开始日期 |
| `date_to` | 创建结束日期 |
| `page` | 页码 |
| `page_size` | 每页数量 |

任务管理操作：

```http
POST   /api/tasks/{task_id}/retry
POST   /api/tasks/{task_id}/cancel
DELETE /api/tasks/{task_id}
```

要求：

- 失败、超时、取消的任务可以重试。
- 等待中的任务可以取消。
- 运行中的任务 v1.1 可以标记取消，但是否能立即停止取决于转换子进程状态。
- 删除任务记录不删除文件和转换结果。

## 9. 管理页面需求

管理页面路径：

```http
GET /web
```

页面要求：

- 未登录时显示登录页。
- 登录后显示管理首页。
- 页面使用系统本地静态资源，不依赖外部 CDN。
- 页面风格简单、清晰、偏管理工具。

页面模块：

### 9.1 登录页

- 用户名输入。
- 密码输入。
- 登录按钮。
- 登录失败提示。

### 9.2 上传解析

- 选择文件。
- 上传后创建异步任务。
- 显示任务状态和进度条。
- 成功后可进入文件详情。

### 9.3 文件管理

- 文件列表。
- 文件名搜索。
- 格式筛选。
- 状态筛选。
- 查看文件详情。
- Markdown 预览。
- 下载 zip。
- 删除缓存。
- 删除文件。
- 重新解析。

### 9.4 任务管理

- 任务列表。
- 状态筛选。
- 进度展示。
- 查看失败原因。
- 重试任务。
- 取消任务。
- 删除任务记录。
- 点击任务进入对应文件详情。

### 9.5 Markdown 预览

- 展示 Markdown 渲染预览。
- 支持查看原始 Markdown 文本。
- 图片链接通过附件接口正常显示。

## 10. 非功能需求

- 保持 v1.0 同步接口兼容。
- 开放 API 不做登录保护。
- 管理 API 和 `/web` 页面要求登录。
- 继续使用 SQLite。
- 继续使用本地文件系统存储。
- 任务队列 v1.1 使用进程内队列。
- 服务重启后，未完成任务标记为失败或取消，不做队列恢复。
- 保持上传大小限制、转换超时和转换并发限制。

## 11. 本版本不做

- OCR。
- 扫描 PDF 识别。
- Redis、Celery 或外部队列。
- 对象存储。
- 多用户和权限体系。
- 外部系统 API 鉴权。
- Webhook 回调。
- 老 Office 格式 `.doc`、`.xls`、`.ppt` 支持。

