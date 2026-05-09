# DocumentToMarkdown v1.1 外部系统接入使用手册

本文档面向需要接入 DocumentToMarkdown 的外部系统开发者，说明项目能力、开放接口、推荐调用流程和注意事项。

## 项目介绍

DocumentToMarkdown 是一个文档转 Markdown 服务，适合部署在本机或可信内网环境中，为业务系统提供统一的文档解析能力。

核心能力：

- 上传 PDF、Word、PPT、Excel、CSV、HTML、TXT、Markdown 等文件。
- 将文档内容转换为 Markdown。
- 提取文档中的图片等附件，并提供独立访问接口。
- 支持同步转换和异步任务转换。
- 支持按任务查询进度，便于外部系统轮询。
- 提供 Markdown、原始文件、附件、Markdown 压缩包下载接口。

安全边界：

- 外部系统使用的基础 API 默认开放，不要求登录。
- 管理页面和管理类 API 要求登录，主要给人工运维使用。
- 当前版本定位为本机或可信内网服务。如果需要暴露到公网，请在网关、反向代理或上层业务系统中增加鉴权、限流和访问控制。

## 快速启动

默认服务地址：

```text
http://127.0.0.1:9527
```

健康检查：

```bash
curl http://127.0.0.1:9527/health
```

返回：

```json
{
  "status": "ok"
}
```

管理页面地址：

```text
http://127.0.0.1:9527/web
```

管理页面需要登录，账号密码配置在 `.env`：

```env
ADMIN_USERNAME=admin
ADMIN_PASSWORD=admin
```

## 外部系统推荐调用流程

推荐外部系统使用异步转换流程：

1. 调用 `POST /api/tasks/convert` 上传文件，获得 `task_id` 和 `file_id`。
2. 每 1 到 3 秒调用 `GET /api/tasks/{task_id}` 查询状态和进度。
3. 当任务状态为 `success` 时，从 `result.markdown_url` 获取 Markdown，或从 `result.download_url` 下载压缩包。
4. 当任务状态为 `failed` 或 `timeout` 时，记录 `error_code` 和 `error_message` 并按业务策略重试或提示人工处理。

状态流转：

```text
queued -> running -> success
queued -> running -> failed
queued -> running -> timeout
queued -> cancelled
```

任务状态说明：

| 状态 | 说明 | 是否终态 |
| --- | --- | --- |
| `queued` | 排队中 | 否 |
| `running` | 转换中 | 否 |
| `success` | 转换成功 | 是 |
| `failed` | 转换失败 | 是 |
| `timeout` | 转换超时 | 是 |
| `cancelled` | 已取消 | 是 |

进度字段说明：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `progress` | integer | 0 到 100 的进度值 |
| `stage` | string | 当前阶段，例如 `queued`、`converting`、`completed` |
| `stage_text` | string | 当前阶段中文描述 |
| `message` | string | 当前阶段中文描述 |

## 开放接口清单

以下接口不要求登录，供其他系统使用。

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `GET` | `/health` | 健康检查 |
| `POST` | `/api/tasks/convert` | 异步上传并创建转换任务 |
| `GET` | `/api/tasks/{task_id}` | 查询任务状态和转换结果 |
| `POST` | `/api/documents/convert` | 同步上传并转换文档 |
| `GET` | `/api/documents/{file_id}` | 查询文档信息 |
| `GET` | `/api/documents/{file_id}/markdown` | 获取 Markdown 原文 |
| `GET` | `/api/documents/{file_id}/original` | 下载原始文件 |
| `GET` | `/api/documents/{file_id}/assets/{asset_name}` | 获取图片等附件 |
| `GET` | `/api/documents/{file_id}/download` | 下载 Markdown 压缩包 |

管理类接口如文件列表、任务列表、删除缓存、删除文件、重试、取消任务等需要登录，不建议外部系统直接依赖。

## 接口详解

### 异步上传转换

`POST /api/tasks/convert`

请求类型：`multipart/form-data`

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `file` | file | 是 | 待转换文档 |

curl 示例：

```bash
curl -X POST "http://127.0.0.1:9527/api/tasks/convert" \
  -F "file=@test.pdf"
```

任务创建响应：

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

如果文件内容已转换过且缓存有效，可能直接返回成功：

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

curl 示例：

```bash
curl "http://127.0.0.1:9527/api/tasks/1789158229000000001"
```

运行中响应：

```json
{
  "status": "running",
  "status_text": "转换中",
  "task_id": "1789158229000000001",
  "file_id": "1789158229000000000",
  "original_filename": "test.pdf",
  "file_format": "pdf",
  "progress": 40,
  "stage": "converting",
  "stage_text": "转换中",
  "message": "开始转换文档",
  "created_at": "2026-05-08 14:30:00",
  "updated_at": "2026-05-08 14:30:03",
  "started_at": "2026-05-08 14:30:01",
  "finished_at": null,
  "result": null,
  "error_code": null,
  "error_message": null
}
```

成功响应：

```json
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
    "metadata": {},
    "warnings": []
  },
  "error_code": null,
  "error_message": null
}
```

失败响应中的任务结构：

```json
{
  "status": "failed",
  "status_text": "失败",
  "task_id": "1789158229000000001",
  "progress": 100,
  "stage": "failed",
  "stage_text": "失败",
  "message": "文档转换失败",
  "result": null,
  "error_code": "convert_failed",
  "error_message": "文档转换失败"
}
```

### 获取文档信息

`GET /api/documents/{file_id}`

curl 示例：

```bash
curl "http://127.0.0.1:9527/api/documents/1789158229000000000"
```

该接口适合在已知 `file_id` 时获取完整文档信息，包括原始文件下载地址和附件列表。

响应字段：

| 字段 | 说明 |
| --- | --- |
| `file_id` | 文档 ID |
| `original_filename` | 原始文件名 |
| `file_format` | 文件格式 |
| `file_size` | 文件大小，单位字节 |
| `status` | 最近一次转换状态 |
| `status_text` | 最近一次转换状态中文描述 |
| `markdown_url` | Markdown 获取地址 |
| `download_url` | Markdown 压缩包下载地址 |
| `original_url` | 原始文件下载地址 |
| `assets` | 附件列表 |
| `metadata` | 转换元数据 |

### 获取 Markdown

`GET /api/documents/{file_id}/markdown`

curl 示例：

```bash
curl "http://127.0.0.1:9527/api/documents/1789158229000000000/markdown"
```

响应类型：

```text
text/markdown; charset=utf-8
```

图片处理建议：

- 如果只是归档或下载结果，优先使用 `/api/documents/{file_id}/download`，压缩包中会包含 `result.md` 和 `assets/`。
- 如果需要在线渲染 Markdown，请将 Markdown 中的相对图片路径转换为附件接口地址。
- 常见相对图片路径包括 `assets/image-001.png` 或 `image-001.png`。
- 转换后的访问地址格式为 `/api/documents/{file_id}/assets/{asset_name}`。

### 获取附件

`GET /api/documents/{file_id}/assets/{asset_name}`

curl 示例：

```bash
curl "http://127.0.0.1:9527/api/documents/1789158229000000000/assets/image-001.png" \
  --output image-001.png
```

附件名称可以从任务结果的 `result.assets` 或文档信息的 `assets` 字段中获取。

### 下载原始文件

`GET /api/documents/{file_id}/original`

curl 示例：

```bash
curl "http://127.0.0.1:9527/api/documents/1789158229000000000/original" \
  --output test.pdf
```

### 下载 Markdown 压缩包

`GET /api/documents/{file_id}/download`

curl 示例：

```bash
curl "http://127.0.0.1:9527/api/documents/1789158229000000000/download" \
  --output result.zip
```

压缩包内容通常包括：

```text
result.md
metadata.json
assets/
```

### 同步上传转换

`POST /api/documents/convert`

同步接口会等待转换完成后返回结果，适合小文件、测试工具或低频调用场景。生产系统批量接入建议使用异步接口。

curl 示例：

```bash
curl -X POST "http://127.0.0.1:9527/api/documents/convert" \
  -F "file=@test.docx"
```

响应结构与异步任务成功后的 `result` 基本一致。

## Python 接入示例

```python
import time
import requests

BASE_URL = "http://127.0.0.1:9527"


def convert_document(path: str) -> dict:
    with open(path, "rb") as file_obj:
        response = requests.post(
            f"{BASE_URL}/api/tasks/convert",
            files={"file": file_obj},
            timeout=60,
        )
    response.raise_for_status()
    task = response.json()

    if task["status"] == "success":
        return task["result"]

    task_id = task["task_id"]
    while True:
        response = requests.get(f"{BASE_URL}/api/tasks/{task_id}", timeout=30)
        response.raise_for_status()
        task = response.json()

        if task["status"] == "success":
            return task["result"]

        if task["status"] in {"failed", "timeout", "cancelled"}:
            raise RuntimeError(task.get("error_message") or task.get("message"))

        time.sleep(2)


result = convert_document("test.pdf")
markdown = requests.get(f"{BASE_URL}{result['markdown_url']}", timeout=30).text
print(markdown[:500])
```

## 错误处理建议

接口错误响应一般为：

```json
{
  "detail": {
    "status": "failed",
    "status_text": "失败",
    "error_code": "unsupported_file_format",
    "message": "不支持的文件格式"
  }
}
```

建议外部系统按以下方式处理：

| 场景 | 建议 |
| --- | --- |
| `unsupported_file_format` | 提示用户文件格式不支持 |
| `file_too_large` | 提示用户压缩文件或联系管理员调整限制 |
| `convert_timeout` | 可稍后重试，或拆分文档 |
| `convert_failed` | 记录文件和错误信息，必要时人工处理 |
| `task_not_found` | 检查 `task_id` 是否正确或任务是否已被管理端删除 |
| `document_not_found` | 检查 `file_id` 是否正确或文档是否已被管理端删除 |

轮询建议：

- 普通文件每 1 到 3 秒查询一次任务状态。
- 大文件或批量任务可以逐步拉长轮询间隔。
- 对 `failed`、`timeout`、`cancelled` 等终态不要继续轮询。
- 同一个文件重复上传可能命中缓存，调用方需要兼容 `task_id=null` 且 `status=success` 的响应。

## 配置与限制

常用服务配置：

| 配置项 | 默认值 | 说明 |
| --- | --- | --- |
| `APP_HOST` | `127.0.0.1` | 服务监听地址 |
| `APP_PORT` | `9527` | 服务端口 |
| `MAX_UPLOAD_SIZE_MB` | `100` | 单文件最大上传大小 |
| `CONVERSION_TIMEOUT_SECONDS` | `300` | 单次转换超时时间 |
| `CONVERSION_CONCURRENCY` | `1` | 转换并发数 |
| `TASK_WORKER_COUNT` | `1` | 异步任务 worker 数量 |
| `DATA_DIR` | `data` | 数据、上传文件和输出目录 |

支持文件格式：

```text
pdf, docx, pptx, xlsx, csv, html, htm, txt, md, markdown
```

## OpenAPI 文档

OpenAPI JSON 文件位于：

```text
docs/DocumentToMarkdown_v1.1_openapi.json
```

开发者可以将该文件导入 Apifox、Postman、Swagger UI 或 OpenAPI Generator。

如果服务正在运行，也可以访问 FastAPI 默认文档页面：

```text
http://127.0.0.1:9527/docs
http://127.0.0.1:9527/redoc
```

## 部署建议

内网部署时建议：

- 将服务部署在业务系统可访问的内网地址。
- 根据文件大小和转换耗时调整 `MAX_UPLOAD_SIZE_MB`、`CONVERSION_TIMEOUT_SECONDS`。
- 对批量调用方做并发控制，避免大量大文件同时提交。
- 定期通过管理页面清理不再需要的文件和缓存。

公网或跨网络访问时建议：

- 不要直接暴露开放 API。
- 在反向代理、API 网关或业务系统侧增加鉴权。
- 增加 IP 白名单、限流、请求体大小限制和日志审计。
