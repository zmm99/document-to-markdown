# DocumentToMarkdown v1.1 接口文档

本文档描述 DocumentToMarkdown v1.1 当前后端接口。接口分为两类：

- 开放 API：用于其他系统上传解析、查询任务状态、获取 Markdown、附件和下载包，默认不要求登录。
- 管理 API：用于管理页面的文件列表、任务列表、删除缓存、重试、取消等操作，要求先登录并携带会话 Cookie。

## 基本信息

- 默认服务地址：`http://127.0.0.1:9527`
- API 前缀：`/api`
- 管理页面：`/web`
- 请求编码：`UTF-8`
- 时间格式：北京时间 `yyyy-MM-dd HH:mm:ss`
- 上传方式：`multipart/form-data`
- Markdown 响应：`text/markdown; charset=utf-8`
- 附件与下载响应：二进制文件流

## 支持格式

| 格式 | 扩展名 |
| --- | --- |
| PDF | `.pdf` |
| Word | `.docx` |
| PowerPoint | `.pptx` |
| Excel | `.xlsx` |
| CSV | `.csv` |
| HTML | `.html`, `.htm` |
| Text | `.txt` |
| Markdown | `.md`, `.markdown` |

## 通用响应约定

成功响应一般包含：

```json
{
  "status": "success",
  "status_text": "成功"
}
```

失败响应一般为：

```json
{
  "detail": {
    "status": "failed",
    "status_text": "失败",
    "error_code": "convert_failed",
    "message": "文档转换失败"
  }
}
```

常见错误码：

| 错误码 | 说明 |
| --- | --- |
| `empty_file` | 上传文件为空 |
| `empty_filename` | 文件名为空 |
| `unsupported_file_format` | 文件格式不支持 |
| `file_too_large` | 文件超过上传大小限制 |
| `upload_save_failed` | 上传文件保存失败 |
| `convert_failed` | 转换失败 |
| `convert_timeout` | 转换超时 |
| `invalid_file_id` | 文件 ID 不合法 |
| `document_not_found` | 文档不存在 |
| `markdown_not_found` | Markdown 结果不存在 |
| `asset_not_found` | 附件不存在 |
| `upload_not_found` | 原始文件不存在 |
| `invalid_task_id` | 任务 ID 不合法 |
| `task_not_found` | 任务不存在 |
| `task_not_cancellable` | 任务不可取消 |
| `task_not_retryable` | 任务不可重试 |
| `task_is_running` | 任务正在运行，不能删除 |
| `document_has_active_task` | 文档存在活跃任务，不能删除 |
| `invalid_date_range` | 日期范围不合法 |
| `unauthorized` | 未登录或会话无效 |
| `invalid_credentials` | 登录账号或密码错误 |

## 开放 API

开放 API 用于其他系统接入，当前不要求登录。

### 健康检查

`GET /health`

用于检查服务是否存活。

响应示例：

```json
{
  "status": "ok",
  "status_text": "正常"
}
```

### 同步转换文档

`POST /api/documents/convert`

同步上传并转换文档。接口会在转换完成后返回结果，适合小文件或调用方希望阻塞等待的场景。较大文件建议使用异步转换接口。

请求类型：`multipart/form-data`

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `file` | file | 是 | 待转换文件 |

响应示例：

```json
{
  "status": "success",
  "status_text": "成功",
  "file_id": "1789158229000000000",
  "file_format": "pdf",
  "cached": false,
  "markdown_url": "/api/documents/1789158229000000000/markdown",
  "download_url": "/api/documents/1789158229000000000/download",
  "assets": [
    {
      "name": "image-001.png",
      "type": "image",
      "url": "/api/documents/1789158229000000000/assets/image-001.png"
    }
  ],
  "metadata": {
    "original_filename": "test.pdf",
    "file_format": "pdf",
    "created_at": "2026-05-08 14:30:00"
  },
  "warnings": []
}
```

说明：

- `file_id` 是系统生成的文档 ID，不再等同于文件 MD5。
- `cached=true` 表示命中了历史转换结果。
- 返回的 `markdown_url`、`download_url`、附件 `url` 均可直接访问。

### 异步提交转换任务

`POST /api/tasks/convert`

上传文件并创建异步转换任务。推荐其他系统优先使用该接口。

请求类型：`multipart/form-data`

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `file` | file | 是 | 待转换文件 |

响应状态码：

- `202 Accepted`：任务已创建或排队。
- `200 OK`：命中缓存，已直接返回成功结果。

任务创建响应示例：

```json
{
  "status": "queued",
  "status_text": "排队中",
  "task_id": "1789158229000000001",
  "file_id": "1789158229000000000",
  "original_filename": "test.pdf",
  "file_format": "pdf",
  "progress": 10,
  "stage": "queued",
  "stage_text": "排队中",
  "message": "任务等待转换",
  "created_at": "2026-05-08 14:30:00",
  "updated_at": "2026-05-08 14:30:00",
  "started_at": null,
  "finished_at": null,
  "result": null,
  "error_code": null,
  "error_message": null
}
```

缓存命中响应示例：

```json
{
  "status": "success",
  "status_text": "成功",
  "task_id": null,
  "file_id": "1789158229000000000",
  "original_filename": "test.pdf",
  "file_format": "pdf",
  "progress": 100,
  "stage": "completed",
  "stage_text": "已完成",
  "message": "命中缓存，转换完成",
  "created_at": "2026-05-08 14:30:00",
  "updated_at": "2026-05-08 14:30:00",
  "started_at": null,
  "finished_at": "2026-05-08 14:30:00",
  "result": {
    "status": "success",
    "status_text": "成功",
    "file_id": "1789158229000000000",
    "file_format": "pdf",
    "cached": true,
    "markdown_url": "/api/documents/1789158229000000000/markdown",
    "download_url": "/api/documents/1789158229000000000/download",
    "assets": [],
    "metadata": {},
    "warnings": []
  },
  "error_code": null,
  "error_message": null
}
```

### 查询任务状态

`GET /api/tasks/{task_id}`

查询异步转换任务状态和进度。

路径参数：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `task_id` | string | 任务 ID |

任务状态：

| 状态 | 说明 |
| --- | --- |
| `queued` | 排队中 |
| `running` | 转换中 |
| `success` | 转换成功 |
| `failed` | 转换失败 |
| `timeout` | 转换超时 |
| `cancelled` | 已取消 |

响应示例：

```json
{
  "status": "running",
  "status_text": "转换中",
  "task_id": "1789158229000000001",
  "file_id": "1789158229000000000",
  "original_filename": "test.pdf",
  "file_format": "pdf",
  "progress": 45,
  "stage": "converting",
  "stage_text": "转换中",
  "message": "开始转换文档",
  "created_at": "2026-05-08 14:30:00",
  "updated_at": "2026-05-08 14:30:05",
  "started_at": "2026-05-08 14:30:01",
  "finished_at": null,
  "result": null,
  "error_code": null,
  "error_message": null
}
```

成功完成后 `result` 中会返回 Markdown、下载包和附件地址。

### 查询文档信息

`GET /api/documents/{file_id}`

查询文档基本信息、转换结果地址、原始文件地址和附件列表。

路径参数：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `file_id` | string | 文档 ID |

响应示例：

```json
{
  "status": "success",
  "status_text": "成功",
  "file_id": "1789158229000000000",
  "original_filename": "test.pdf",
  "file_format": "pdf",
  "mime_type": "application/pdf",
  "file_size": 102400,
  "storage_date": "20260508",
  "created_at": "2026-05-08 14:30:00",
  "updated_at": "2026-05-08 14:30:10",
  "markdown_url": "/api/documents/1789158229000000000/markdown",
  "download_url": "/api/documents/1789158229000000000/download",
  "original_url": "/api/documents/1789158229000000000/original",
  "assets": [
    {
      "name": "image-001.png",
      "type": "image",
      "url": "/api/documents/1789158229000000000/assets/image-001.png",
      "size": 20480
    }
  ],
  "metadata": {
    "page_count": 3
  },
  "warnings": [],
  "parse_record": {
    "status": "success",
    "status_text": "成功"
  }
}
```

### 获取 Markdown

`GET /api/documents/{file_id}/markdown`

获取转换后的 Markdown 原文。

响应类型：`text/markdown; charset=utf-8`

### 下载原始文件

`GET /api/documents/{file_id}/original`

下载上传时保存的原始文件。

响应类型：二进制文件流。

### 获取附件

`GET /api/documents/{file_id}/assets/{asset_name}`

获取转换过程中导出的附件，主要包括图片。

路径参数：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `file_id` | string | 文档 ID |
| `asset_name` | string | 附件文件名，例如 `image-001.png` |

响应类型：二进制文件流。

### 下载 Markdown 压缩包

`GET /api/documents/{file_id}/download`

下载转换结果压缩包。压缩包通常包含：

- `result.md`
- `metadata.json`
- `assets/` 附件目录

响应类型：`application/zip`

## 登录 API

登录 API 主要供管理页面使用。登录成功后服务会写入 HttpOnly Cookie。

### 登录

`POST /api/auth/login`

请求类型：`application/json`

请求体：

```json
{
  "username": "admin",
  "password": "admin"
}
```

响应示例：

```json
{
  "status": "success",
  "status_text": "成功",
  "username": "admin"
}
```

账号密码来自 `.env`：

```env
ADMIN_USERNAME=admin
ADMIN_PASSWORD=admin
SESSION_SECRET=change-me
SESSION_EXPIRE_HOURS=8
```

### 退出登录

`POST /api/auth/logout`

清除当前会话 Cookie。

响应示例：

```json
{
  "status": "success",
  "status_text": "成功"
}
```

### 当前登录用户

`GET /api/auth/me`

响应示例：

```json
{
  "status": "success",
  "status_text": "成功",
  "username": "admin"
}
```

## 管理 API

管理 API 要求登录。调用方需要先执行 `/api/auth/login`，再携带服务返回的 Cookie。

### 文件列表

`GET /api/documents`

查询已上传和已转换的文件列表。

查询参数：

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `q` | string | 否 | 文件名或文件 ID 关键字 |
| `file_format` | string | 否 | 文件格式，例如 `pdf` |
| `start_date` | string | 否 | 开始时间，支持 `yyyy-MM-dd` 或 `yyyy-MM-dd HH:mm:ss` |
| `end_date` | string | 否 | 结束时间，支持 `yyyy-MM-dd` 或 `yyyy-MM-dd HH:mm:ss` |
| `limit` | integer | 否 | 每页数量，默认 20，最大 100 |
| `offset` | integer | 否 | 偏移量，默认 0 |

响应示例：

```json
{
  "status": "success",
  "status_text": "成功",
  "total": 1,
  "items": [
    {
      "file_id": "1789158229000000000",
      "original_filename": "test.pdf",
      "file_format": "pdf",
      "file_size": 102400,
      "status": "success",
      "status_text": "成功",
      "asset_count": 0,
      "created_at": "2026-05-08 14:30:00",
      "updated_at": "2026-05-08 14:30:10",
      "markdown_url": "/api/documents/1789158229000000000/markdown",
      "download_url": "/api/documents/1789158229000000000/download"
    }
  ]
}
```

### 重新转换文件

`POST /api/documents/{file_id}/reconvert`

为已有文件创建重新转换任务。

响应示例：

```json
{
  "status": "queued",
  "status_text": "排队中",
  "task_id": "1789158229000000002",
  "file_id": "1789158229000000000",
  "progress": 10,
  "stage": "queued",
  "stage_text": "排队中",
  "message": "重新转换任务等待转换"
}
```

### 删除文件缓存

`DELETE /api/documents/{file_id}/cache`

删除指定文档的转换结果和附件缓存，保留文档记录和原始文件。

响应示例：

```json
{
  "status": "success",
  "status_text": "成功",
  "file_id": "1789158229000000000",
  "deleted_parse_records": 1,
  "deleted_assets": 0,
  "deleted_output_dirs": 1,
  "warnings": []
}
```

### 删除文件

`DELETE /api/documents/{file_id}`

删除指定文档、转换记录、任务记录、原始文件和输出文件。

响应示例：

```json
{
  "status": "success",
  "status_text": "成功",
  "file_id": "1789158229000000000"
}
```

### 任务列表

`GET /api/tasks`

查询转换任务列表。

查询参数：

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `status` | string | 否 | 任务状态 |
| `q` | string | 否 | 文件名、文件 ID 或任务 ID 关键字 |
| `start_date` | string | 否 | 开始时间，支持 `yyyy-MM-dd` 或 `yyyy-MM-dd HH:mm:ss` |
| `end_date` | string | 否 | 结束时间，支持 `yyyy-MM-dd` 或 `yyyy-MM-dd HH:mm:ss` |
| `limit` | integer | 否 | 每页数量，默认 20，最大 100 |
| `offset` | integer | 否 | 偏移量，默认 0 |

响应示例：

```json
{
  "status": "success",
  "status_text": "成功",
  "total": 1,
  "items": [
    {
      "status": "success",
      "status_text": "成功",
      "task_id": "1789158229000000001",
      "file_id": "1789158229000000000",
      "original_filename": "test.pdf",
      "file_format": "pdf",
      "progress": 100,
      "stage": "completed",
      "stage_text": "已完成",
      "message": "文档转换完成",
      "created_at": "2026-05-08 14:30:00",
      "updated_at": "2026-05-08 14:30:10",
      "started_at": "2026-05-08 14:30:01",
      "finished_at": "2026-05-08 14:30:10",
      "result": {
        "markdown_url": "/api/documents/1789158229000000000/markdown",
        "download_url": "/api/documents/1789158229000000000/download"
      },
      "error_code": null,
      "error_message": null
    }
  ]
}
```

### 取消任务

`POST /api/tasks/{task_id}/cancel`

取消尚未完成的任务。

响应示例：

```json
{
  "status": "cancelled",
  "status_text": "已取消",
  "task_id": "1789158229000000001",
  "progress": 100,
  "stage": "cancelled",
  "stage_text": "已取消",
  "message": "任务已取消"
}
```

### 重试任务

`POST /api/tasks/{task_id}/retry`

对失败、超时或已取消任务创建一个新的重试任务。

响应示例：

```json
{
  "status": "queued",
  "status_text": "排队中",
  "task_id": "1789158229000000003",
  "file_id": "1789158229000000000",
  "progress": 10,
  "stage": "queued",
  "stage_text": "排队中",
  "message": "重试任务等待转换"
}
```

### 删除任务

`DELETE /api/tasks/{task_id}`

删除非运行中的任务记录。

响应示例：

```json
{
  "status": "success",
  "status_text": "成功",
  "deleted_task_id": "1789158229000000001",
  "deleted_tasks": 1
}
```

## 管理页面

`GET /web`

打开内置管理页面。页面能力包括：

- 登录和退出。
- 上传文件并创建解析任务。
- 查看任务列表、任务状态和进度。
- 查询文件列表，支持关键字、格式和日期范围筛选。
- 预览 Markdown，查看文件详情。
- 下载原始文件和 Markdown 压缩包。
- 删除缓存、删除文件、取消任务、重试任务。

## 配置项

常用配置来自 `.env`：

```env
APP_HOST=127.0.0.1
APP_PORT=9527
API_PREFIX=/api
DATA_DIR=data
MAX_UPLOAD_SIZE_MB=100
CONVERSION_TIMEOUT_SECONDS=300
CONVERSION_CONCURRENCY=1
TASK_WORKER_COUNT=1
ADMIN_USERNAME=admin
ADMIN_PASSWORD=admin
SESSION_SECRET=change-me
SESSION_EXPIRE_HOURS=8
```

说明：

- `MAX_UPLOAD_SIZE_MB` 控制单文件上传大小。
- `CONVERSION_TIMEOUT_SECONDS` 控制单次转换超时时间。
- `CONVERSION_CONCURRENCY` 控制转换并发隔离。
- `TASK_WORKER_COUNT` 控制异步任务 worker 数量。
- 如果服务暴露到非可信网络，建议通过网关、反向代理或内网访问控制保护开放 API。
