# DocumentToMarkdown v1.1 设计文档

## 1. 设计目标

v1.1 在 v1.0 的同步转换 API 之上增加异步任务、文件列表、任务列表和 `/web` 管理页面。

设计原则：

- 保留 v1.0 已有 API 行为。
- 开放 API 不加登录保护，方便其他系统集成。
- 管理页面和管理类 API 要求登录。
- 继续使用 SQLite 和本地文件系统。
- 避免引入 Redis、Celery、Node 构建链等重依赖。
- 任务进度使用阶段进度，先保证可观测和可轮询。

## 2. 总体架构

```text
外部系统
  |
  | 开放 API
  v
FastAPI
  |-- documents API
  |-- tasks API
  |-- auth API
  |-- web static
  |
  |-- SQLite
  |     |-- documents
  |     |-- parse_records
  |     |-- document_assets
  |     |-- conversion_tasks
  |
  |-- 本地文件系统 data/
  |
  |-- 进程内任务队列
        |
        v
      task worker
        |
        v
      conversion subprocess
```

## 3. API 分层

### 3.1 开放 API

开放 API 不要求登录。

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/documents/convert` | v1.0 同步转换接口 |
| POST | `/api/tasks/convert` | v1.1 异步转换接口 |
| GET | `/api/tasks/{task_id}` | 查询任务状态和进度 |
| GET | `/api/documents/{file_id}` | 获取文档信息 |
| GET | `/api/documents/{file_id}/markdown` | 获取 Markdown |
| GET | `/api/documents/{file_id}/assets/{asset_name}` | 获取附件 |
| GET | `/api/documents/{file_id}/download` | 下载完整结果 zip |

### 3.2 管理 API

管理 API 要求登录。

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/documents` | 文件列表 |
| POST | `/api/documents/{file_id}/reconvert` | 重新解析文件 |
| DELETE | `/api/documents/{file_id}/cache` | 删除解析缓存 |
| DELETE | `/api/documents/{file_id}` | 删除文件 |
| GET | `/api/tasks` | 任务列表 |
| POST | `/api/tasks/{task_id}/retry` | 重试任务 |
| POST | `/api/tasks/{task_id}/cancel` | 取消任务 |
| DELETE | `/api/tasks/{task_id}` | 删除任务记录 |
| POST | `/api/auth/logout` | 退出登录 |
| GET | `/api/auth/me` | 当前登录状态 |

### 3.3 认证 API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/auth/login` | 登录 |

登录成功后写入 HTTP-only cookie。

## 4. 配置设计

新增配置：

```env
ADMIN_USERNAME=admin
ADMIN_PASSWORD=change-me
SESSION_SECRET=change-me-too
SESSION_EXPIRE_HOURS=12
TASK_WORKER_COUNT=1
```

沿用 v1.0 配置：

```env
APP_NAME=DocumentToMarkdown
DATA_DIR=./data
MAX_UPLOAD_SIZE_MB=100
API_PREFIX=/api
CONVERT_TIMEOUT_SECONDS=300
MAX_CONCURRENT_CONVERSIONS=2
DOCLING_ARTIFACTS_PATH=./models/docling
```

说明：

- `TASK_WORKER_COUNT` v1.1 默认 1。
- `MAX_CONCURRENT_CONVERSIONS` 继续限制实际转换并发。
- 管理密码直接来自 `.env`，不进入数据库。

## 5. 数据库设计

### 5.1 现有表

继续使用 v1.0 表：

- `documents`
- `parse_records`
- `document_assets`

其中：

- `documents.id` 为对外 `file_id`。
- `documents.md5` 仅用于内部缓存查询。
- `parse_records` 继续记录每次转换结果。
- `document_assets` 继续记录图片附件。

### 5.2 新增 conversion_tasks

```sql
CREATE TABLE IF NOT EXISTS conversion_tasks (
    id TEXT PRIMARY KEY,
    document_id TEXT,
    file_format TEXT NOT NULL,
    original_filename TEXT NOT NULL,
    file_size INTEGER NOT NULL,
    status TEXT NOT NULL,
    progress_percent INTEGER NOT NULL DEFAULT 0,
    progress_stage TEXT NOT NULL,
    progress_message TEXT,
    engine TEXT,
    error_code TEXT,
    error_message TEXT,
    parse_record_id INTEGER,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(document_id) REFERENCES documents(id),
    FOREIGN KEY(parse_record_id) REFERENCES parse_records(id)
);
```

建议索引：

```sql
CREATE INDEX IF NOT EXISTS idx_conversion_tasks_status
ON conversion_tasks(status);

CREATE INDEX IF NOT EXISTS idx_conversion_tasks_document_id
ON conversion_tasks(document_id);

CREATE INDEX IF NOT EXISTS idx_conversion_tasks_created_at
ON conversion_tasks(created_at);
```

## 6. 任务模型设计

### 6.1 状态

```text
queued
running
success
failed
timeout
cancelled
```

### 6.2 进度

任务表保存三个进度字段：

- `progress_percent`
- `progress_stage`
- `progress_message`

对外统一返回：

```json
{
  "percent": 40,
  "stage": "converting",
  "message": "converting document"
}
```

进度阶段：

| 状态 | percent | stage | message |
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

## 7. 异步转换流程

### 7.1 创建任务流程

```text
1. POST /api/tasks/convert 上传文件
2. 校验文件名、格式和大小
3. 分块写入临时文件并计算 md5
4. 查询 documents 是否已有 md5 + file_format
5. 无记录则生成 file_id
6. 保存原始文件到 data/uploads/yyyyMMdd/{file_id}.{ext}
7. 写入或更新 documents
8. 创建 conversion_tasks，状态为 queued，进度 20
9. 将 task_id 放入进程内队列
10. 返回 task_id、file_id、status_url、document_url
```

### 7.2 worker 执行流程

```text
1. worker 从队列获取 task_id
2. 将任务状态更新为 running，进度 40
3. 检查任务是否已被取消
4. 查询 document 和上传文件路径
5. 调用转换子进程执行转换
6. 转换成功后写 result.md、metadata.json 和附件
7. 写入 parse_records 和 document_assets
8. 更新任务为 success，进度 100
9. 转换失败则更新任务为 failed 或 timeout，进度 100
```

### 7.3 缓存命中流程

创建异步任务时，如果 `md5 + file_format` 已有可用成功缓存：

```text
1. 仍创建 task 记录
2. task 直接标记为 success
3. progress 直接为 100
4. result 指向已有文档结果
5. 不重新入队转换
```

说明：

- 这样外部系统始终通过同一套任务接口交互。
- 缓存命中也有 `task_id`，便于调用方统一处理。

## 8. 同步接口兼容

继续保留：

```http
POST /api/documents/convert
```

行为保持 v1.0：

- 请求等待转换完成。
- 成功后返回文档结果。
- 缓存命中返回 `cached: true`。

同步接口不创建 `conversion_tasks` 记录，避免 v1.0 调用方受到影响。

## 9. 任务操作设计

### 9.1 重试任务

```http
POST /api/tasks/{task_id}/retry
```

规则：

- 仅 `failed`、`timeout`、`cancelled` 任务可重试。
- 重试时创建新任务，返回新的 `task_id`。
- 原任务保留。

### 9.2 取消任务

```http
POST /api/tasks/{task_id}/cancel
```

规则：

- `queued` 任务可直接标记为 `cancelled`。
- `running` 任务可先标记取消请求。
- v1.1 若无法中断正在运行的转换子进程，可等待子进程结束后按取消状态收口。
- 后续版本可增强为强制停止子进程。

### 9.3 删除任务记录

```http
DELETE /api/tasks/{task_id}
```

规则：

- 删除任务记录不删除文档、Markdown、附件或缓存。
- 运行中的任务不允许删除，需先取消。

## 10. 文件管理设计

### 10.1 文件列表

```http
GET /api/documents
```

查询参数：

| 参数 | 说明 |
| --- | --- |
| `keyword` | 原始文件名模糊搜索 |
| `file_format` | 文件格式 |
| `status` | 最近转换状态 |
| `date_from` | 上传开始日期 |
| `date_to` | 上传结束日期 |
| `page` | 页码，默认 1 |
| `page_size` | 每页数量，默认 20 |

返回字段：

```json
{
  "items": [
    {
      "file_id": "311234567890123000",
      "original_filename": "demo.pdf",
      "file_format": "pdf",
      "file_size": 1024,
      "status": "success",
      "created_at": "2026-05-08 16:30:00",
      "updated_at": "2026-05-08 16:30:10",
      "markdown_url": "/api/documents/311234567890123000/markdown"
    }
  ],
  "page": 1,
  "page_size": 20,
  "total": 1
}
```

### 10.2 重新解析

```http
POST /api/documents/{file_id}/reconvert
```

规则：

- 要求登录。
- 使用已保存原始上传文件创建一个新的异步任务。
- 返回新的 `task_id`。

### 10.3 删除缓存

沿用 v1.0：

```http
DELETE /api/documents/{file_id}/cache
```

规则：

- 删除解析记录。
- 删除附件记录。
- 删除输出目录。
- 保留 documents 记录和原始上传文件。

### 10.4 删除文件

```http
DELETE /api/documents/{file_id}
```

规则：

- 删除 documents 记录。
- 删除 parse_records。
- 删除 document_assets。
- 删除输出目录。
- 删除原始上传文件。
- 删除文件前管理页面需要二次确认。

## 11. 登录和会话设计

### 11.1 登录接口

```http
POST /api/auth/login
Content-Type: application/json
```

请求：

```json
{
  "username": "admin",
  "password": "change-me"
}
```

成功：

```json
{
  "status": "success",
  "username": "admin"
}
```

失败：

```json
{
  "detail": {
    "status": "failed",
    "error_code": "invalid_credentials",
    "message": "invalid username or password"
  }
}
```

### 11.2 Cookie

Cookie 建议：

- 名称：`dtm_session`
- `HttpOnly`
- `SameSite=Lax`
- 有效期由 `SESSION_EXPIRE_HOURS` 控制。

Session 内容：

```json
{
  "username": "admin",
  "expires_at": "2026-05-08T20:00:00+08:00"
}
```

Session 使用 `SESSION_SECRET` 签名，避免被客户端伪造。

## 12. 管理页面设计

### 12.1 路由

管理页面路径：

```http
GET /web
GET /web/{path:path}
```

静态文件目录：

```text
app/web/static/
  index.html
  app.js
  style.css
```

### 12.2 页面结构

页面包括：

- 登录页。
- 上传解析。
- 文件管理。
- 任务管理。
- 文件详情。
- Markdown 预览。

### 12.3 交互设计

上传解析：

```text
选择文件 -> POST /api/tasks/convert -> 轮询 GET /api/tasks/{task_id} -> 成功后显示详情入口
```

文件管理：

```text
GET /api/documents -> 列表 -> 查看详情 / 预览 / 下载 / 删除缓存 / 删除文件 / 重新解析
```

任务管理：

```text
GET /api/tasks -> 列表 -> 查看任务详情 / 重试 / 取消 / 删除任务记录
```

Markdown 预览：

- 默认显示渲染预览。
- 提供原始 Markdown 文本切换。
- 图片使用 `/api/documents/{file_id}/assets/{asset_name}`。

## 13. 模块划分

建议新增模块：

```text
app/
  api/
    auth.py
    tasks.py
    web.py
  core/
    auth.py
    task_queue.py
  db/
    task_repository.py
  web/
    static/
      index.html
      app.js
      style.css
```

职责：

- `api/auth.py`：登录、退出、当前用户。
- `api/tasks.py`：异步任务开放接口和管理接口。
- `api/web.py`：管理页面静态资源。
- `core/auth.py`：session 签名和登录校验。
- `core/task_queue.py`：进程内队列和 worker。
- `db/task_repository.py`：任务表读写。

## 14. 启动和恢复设计

服务启动时：

```text
1. 初始化数据库 schema
2. 将 queued/running 的历史任务标记为 failed 或 cancelled
3. 启动 task worker
4. 挂载 /web 静态页面
```

说明：

- v1.1 不恢复服务重启前未完成的队列任务。
- 管理员可在页面中重试失败任务。

## 15. 错误码

新增错误码：

| error_code | 说明 |
| --- | --- |
| `task_not_found` | 任务不存在 |
| `task_not_retryable` | 当前任务状态不允许重试 |
| `task_not_cancellable` | 当前任务状态不允许取消 |
| `task_running` | 运行中的任务不能删除 |
| `invalid_credentials` | 登录失败 |
| `not_authenticated` | 未登录 |
| `session_expired` | 登录已过期 |
| `document_delete_failed` | 删除文件失败 |

沿用 v1.0 错误码：

- `empty_file`
- `file_too_large`
- `unsupported_file_format`
- `invalid_file_id`
- `document_not_found`
- `markdown_not_found`
- `asset_not_found`
- `convert_failed`
- `convert_timeout`
- `converter_dependency_missing`

## 16. 测试范围

必须覆盖：

- 同步转换接口仍可用。
- 异步转换接口创建任务。
- 任务状态从 queued/running 到 success。
- 缓存命中时异步任务直接 success。
- 任务失败返回错误码和进度 100。
- 文件列表分页和筛选。
- 任务列表分页和筛选。
- 登录成功和失败。
- 未登录访问管理 API 返回 401。
- 开放 API 未登录可访问。
- 删除缓存。
- 删除文件。
- 重新解析。
- 管理页面静态资源可访问。

## 17. 兼容性

- v1.0 同步接口保留。
- v1.0 文档结果获取接口保留。
- v1.0 删除缓存接口路径保留，但 v1.1 起要求登录。
- `file_id` 继续使用 v1.0 后期引入的雪花 ID。
- 旧 32 位 md5 `file_id` 可在过渡期继续读取。

## 18. 后续版本预留

v1.2 可考虑：

- OCR。
- Webhook 回调。
- API Token。
- Redis/Celery 持久化任务队列。
- Markdown 后处理增强。
- 老 Office 格式支持。

