# DocumentToMarkdown v1.2 接口文档

本文档面向需要集成 DocumentToMarkdown 的外部系统。v1.2 在 v1.1 同步转换、异步任务、文件查询、附件下载和管理页面基础上，新增 OCR 和 PP-StructureV3 复杂扫描版面解析能力。

## 1. 基本信息

- 默认服务地址：`http://127.0.0.1:9527`
- API 前缀：`/api`
- 管理页面：`/web`
- 请求编码：`UTF-8`
- 时间格式：北京时间 `yyyy-MM-dd HH:mm:ss`
- 上传方式：`multipart/form-data`
- Markdown 响应：`text/markdown; charset=utf-8`
- 下载包响应：`application/zip`

开放 API 默认不要求登录，适合内网系统集成。管理页面和管理类 API 要求登录。

## 2. 支持格式

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
| Image | `.png`, `.jpg`, `.jpeg` |

## 3. OCR 和版面参数

`POST /api/documents/convert` 和 `POST /api/tasks/convert` 都支持以下表单参数：

| 参数 | 类型 | 必填 | 默认值 | 可选值 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `file` | file | 是 | - | - | 待转换文件 |
| `ocr_mode` | string | 否 | `auto` | `off`, `auto`, `full` | OCR 策略 |
| `layout_engine` | string | 否 | `auto` | `auto`, `docling`, `ppstructure` | 版面解析路线 |

参数语义：

- `ocr_mode=off`：关闭 OCR，保持普通电子文档转换行为。
- `ocr_mode=auto`：默认值，自动判断是否需要 OCR。
- `ocr_mode=full`：强制 OCR，适合整份扫描件。
- `layout_engine=auto`：自动选择 Docling 或 PP-StructureV3。
- `layout_engine=docling`：强制 Docling 路线，PDF OCR 使用 RapidOCR。
- `layout_engine=ppstructure`：强制 PP-StructureV3 路线，仅支持 PDF。
- PNG/JPG/JPEG inputs are treated as single-page documents; the original image is always preserved as an asset. `ocr_mode=off` does not extract text, while `ocr_mode=auto/full` uses RapidOCR to append image text.

参数冲突：

- `ocr_mode=off&layout_engine=ppstructure` 会返回 400，错误码为 `conflicting_layout_options`。

## 4. 推荐调用流程

生产系统建议使用异步任务接口：

1. 调用 `POST /api/tasks/convert` 上传文件，获得 `task_id` 和 `file_id`。
2. 每 1 到 3 秒调用 `GET /api/tasks/{task_id}` 查询任务状态。
3. 状态为 `success` 时，读取 `result.markdown_url` 或 `result.download_url`。
4. 状态为 `failed`、`timeout`、`cancelled` 时，记录 `error_code` 和 `error_message`。

状态流转：

```text
queued -> running -> success
queued -> running -> failed
queued -> running -> timeout
queued -> cancelled
```

## 5. 开放 API

以下接口默认不鉴权。

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `GET` | `/health` | 健康检查 |
| `POST` | `/api/tasks/convert` | 异步上传并创建转换任务 |
| `GET` | `/api/tasks/{task_id}` | 查询任务状态 |
| `POST` | `/api/documents/convert` | 同步上传并转换文档 |
| `GET` | `/api/documents/{file_id}` | 查询文档信息 |
| `GET` | `/api/documents/{file_id}/markdown` | 获取 Markdown |
| `GET` | `/api/documents/{file_id}/original` | 下载原始文件 |
| `GET` | `/api/documents/{file_id}/assets/{asset_name}` | 获取附件 |
| `GET` | `/api/documents/{file_id}/download` | 下载 Markdown zip 包 |

## 6. 健康检查

`GET /health`

响应：

```json
{
  "status": "ok",
  "status_text": "正常"
}
```

## 7. 异步转换

`POST /api/tasks/convert`

请求类型：`multipart/form-data`

curl 示例：

```bash
curl -X POST "http://127.0.0.1:9527/api/tasks/convert" \
  -F "file=@scan.pdf" \
  -F "ocr_mode=auto" \
  -F "layout_engine=auto"
```

任务创建响应状态码：

- `202 Accepted`：已创建任务。
- `200 OK`：命中缓存，直接返回成功任务。

任务创建响应示例：

```json
{
  "task_id": "327705216172429312",
  "status": "queued",
  "status_text": "排队中",
  "progress": 10,
  "stage": "queued",
  "stage_text": "排队中",
  "message": "任务等待转换",
  "file_id": "327705216168235008",
  "original_filename": "scan.pdf",
  "file_format": "pdf",
  "cached": false,
  "options": {
    "version": 1,
    "requested": {
      "ocr_mode": "auto",
      "layout_engine": "auto"
    },
    "option_hash": "a366010d9d2846902aea377a5a94d2a7b665e635508d5d1474cfe8bc3e538c51"
  },
  "status_url": "/api/tasks/327705216172429312",
  "document_url": "/api/documents/327705216168235008",
  "markdown_url": "/api/documents/327705216168235008/markdown",
  "download_url": "/api/documents/327705216168235008/download",
  "created_at": "2026-06-23 10:20:00",
  "started_at": null,
  "finished_at": null,
  "updated_at": "2026-06-23 10:20:00",
  "result": null,
  "error_code": null,
  "error_message": null
}
```

## 8. 查询任务状态

`GET /api/tasks/{task_id}`

curl 示例：

```bash
curl "http://127.0.0.1:9527/api/tasks/327705216172429312"
```

成功任务响应示例：

```json
{
  "task_id": "327705216172429312",
  "status": "success",
  "status_text": "成功",
  "progress": 100,
  "stage": "completed",
  "stage_text": "已完成",
  "message": "文档转换完成",
  "file_id": "327705216168235008",
  "original_filename": "scan.pdf",
  "file_format": "pdf",
  "cached": false,
  "options": {
    "requested": {
      "ocr_mode": "auto",
      "layout_engine": "auto"
    },
    "option_hash": "a366010d9d2846902aea377a5a94d2a7b665e635508d5d1474cfe8bc3e538c51"
  },
  "result": {
    "file_id": "327705216168235008",
    "status": "success",
    "status_text": "成功",
    "file_format": "pdf",
    "cached": false,
    "markdown_url": "/api/documents/327705216168235008/markdown",
    "download_url": "/api/documents/327705216168235008/download",
    "assets": [
      {
        "name": "image-001.png",
        "content_type": "image/png",
        "url": "/api/documents/327705216168235008/assets/image-001.png?option_hash=a366010d9d2846902aea377a5a94d2a7b665e635508d5d1474cfe8bc3e538c51"
      }
    ],
    "metadata": {
      "engine": "ppstructure",
      "source_format": "pdf",
      "requested": {
        "ocr_mode": "auto",
        "layout_engine": "auto"
      },
      "actual": {
        "layout_engine": "ppstructure",
        "ocr_applied": true,
        "reason": "scanned_pdf_image_only"
      },
      "pages": {
        "page_count": 66,
        "source": "ppstructure",
        "items": [
          {
            "page": 1,
            "markdown_start_line": 1,
            "markdown_end_line": 35,
            "asset_names": ["image-001.png"],
            "ocr_applied": true,
            "fallback": null
          }
        ]
      },
      "option_hash": "a366010d9d2846902aea377a5a94d2a7b665e635508d5d1474cfe8bc3e538c51"
    },
    "warnings": []
  },
  "error_code": null,
  "error_message": null
}
```

失败任务响应示例：

```json
{
  "task_id": "327705216172429312",
  "status": "failed",
  "status_text": "失败",
  "progress": 100,
  "stage": "failed",
  "stage_text": "失败",
  "message": "文档转换失败",
  "result": null,
  "error_code": "ppstructure_unavailable",
  "error_message": "PP-StructureV3服务未配置"
}
```

## 9. 同步转换

`POST /api/documents/convert`

同步接口会等待转换完成后返回结果，适合小文件、测试工具或低频调用场景。

curl 示例：

```bash
curl -X POST "http://127.0.0.1:9527/api/documents/convert" \
  -F "file=@scan.pdf" \
  -F "ocr_mode=full" \
  -F "layout_engine=ppstructure"
```

响应结构与异步任务成功后的 `result` 基本一致：

```json
{
  "file_id": "327705216168235008",
  "status": "success",
  "status_text": "成功",
  "file_format": "pdf",
  "cached": false,
  "markdown_url": "/api/documents/327705216168235008/markdown",
  "download_url": "/api/documents/327705216168235008/download",
  "assets": [],
  "metadata": {
    "engine": "ppstructure",
    "requested": {
      "ocr_mode": "full",
      "layout_engine": "ppstructure"
    },
    "actual": {
      "layout_engine": "ppstructure",
      "ocr_applied": true,
      "reason": "requested_ppstructure"
    },
    "pages": {
      "page_count": 12,
      "source": "ppstructure",
      "items": [
        {
          "page": 1,
          "markdown_start_line": 1,
          "markdown_end_line": 35,
          "asset_names": ["image-001.png"],
          "ocr_applied": true,
          "fallback": null
        }
      ]
    }
  },
  "warnings": []
}
```

## 10. 查询文档信息

`GET /api/documents/{file_id}`

返回文档基本信息、最近一次可用转换结果、附件和 metadata。

curl 示例：

```bash
curl "http://127.0.0.1:9527/api/documents/327705216168235008"
```

关键字段：

| 字段 | 说明 |
| --- | --- |
| `file_id` | 文档 ID |
| `original_filename` | 原始文件名 |
| `file_format` | 文件格式 |
| `file_size` | 文件大小，单位字节 |
| `status` | 最近一次转换状态 |
| `markdown_url` | Markdown 获取地址 |
| `download_url` | Markdown zip 包地址 |
| `original_url` | 原始文件下载地址 |
| `assets` | 附件列表 |
| `metadata` | 转换元数据 |
| `warnings` | 转换过程警告 |

## 11. 获取 Markdown

`GET /api/documents/{file_id}/markdown`

响应类型：`text/markdown; charset=utf-8`

curl 示例：

```bash
curl "http://127.0.0.1:9527/api/documents/327705216168235008/markdown"
```

Markdown 中图片会尽量引用本服务附件地址。调用方在线渲染时，应确保能够访问 `/api/documents/{file_id}/assets/{asset_name}`。

## 12. 获取附件

`GET /api/documents/{file_id}/assets/{asset_name}`

curl 示例：

```bash
curl "http://127.0.0.1:9527/api/documents/327705216168235008/assets/image-001.png?option_hash=a366010d9d2846902aea377a5a94d2a7b665e635508d5d1474cfe8bc3e538c51" \
  --output image-001.png
```

说明：

- `assets[].url` 中可能带有 `option_hash` 查询参数，用于区分同一文件不同 OCR/layout 参数下的附件。
- 外部系统应优先使用接口返回的完整 `assets[].url`，不要自行拼接。

## 13. 下载结果包

`GET /api/documents/{file_id}/download`

curl 示例：

```bash
curl "http://127.0.0.1:9527/api/documents/327705216168235008/download" \
  --output result.zip
```

zip 内容：

```text
result.md
metadata.json
assets/
```

zip 内 `result.md` 会把本服务附件地址改为本地相对路径，例如：

```markdown
![stamp](assets/image-001.png)
```

因此解压后在支持本地相对图片的 Markdown 查看器中打开 `result.md`，可以直接读取同级 `assets/` 目录下的图片。外部 URL 图片不会被改写。

建议需要归档或跨系统传输时优先使用 zip 包，避免遗漏图片附件。

## 14. 下载原始文件

`GET /api/documents/{file_id}/original`

curl 示例：

```bash
curl "http://127.0.0.1:9527/api/documents/327705216168235008/original" \
  --output scan.pdf
```

## 15. metadata 说明

metadata 会记录请求参数、实际路线和选择原因：

```json
{
  "engine": "ppstructure",
  "source_format": "pdf",
  "requested": {
    "ocr_mode": "auto",
    "layout_engine": "auto"
  },
  "actual": {
    "layout_engine": "ppstructure",
    "ocr_applied": true,
    "reason": "scanned_pdf_image_only"
  },
  "ppstructure": {
    "api_url": "http://192.168.1.4:9528/layout-parsing",
    "page_count": 66,
    "saved_asset_count": 18,
    "use_table_recognition": true,
    "use_seal_recognition": true,
    "fallback": {
      "mode": "paged_retry",
      "reason": "large_pdf",
      "page_timeout_seconds": 60,
      "preprocessed_pages": [],
      "image_fallback_pages": [27]
    }
  },
  "pages": {
    "page_count": 66,
    "source": "ppstructure",
    "items": [
      {
        "page": 1,
        "markdown_start_line": 1,
        "markdown_end_line": 35,
        "asset_names": ["image-001.png"],
        "ocr_applied": true,
        "fallback": null
      },
      {
        "page": 27,
        "markdown_start_line": 860,
        "markdown_end_line": 862,
        "asset_names": ["image-018.jpg"],
        "ocr_applied": true,
        "fallback": "image_preserved_after_ocr_timeout"
      }
    ]
  },
  "option_hash": "a366010d9d2846902aea377a5a94d2a7b665e635508d5d1474cfe8bc3e538c51"
}
```

`metadata.pages` 说明：

| 字段 | 说明 |
| --- | --- |
| `pages.page_count` | 原始文档页数 |
| `pages.source` | 页面信息来源，当前可能为 `ppstructure` 或 `pdf_preflight` |
| `pages.items[].page` | 原始页码，从 1 开始 |
| `pages.items[].markdown_start_line` | 该页内容在最终 Markdown 中的起始行；没有可靠映射时为 `null` |
| `pages.items[].markdown_end_line` | 该页内容在最终 Markdown 中的结束行；没有可靠映射时为 `null` |
| `pages.items[].asset_names` | 该页导出的本地附件文件名 |
| `pages.items[].ocr_applied` | 该页是否经过 OCR/结构化解析 |
| `pages.items[].fallback` | 页级兜底原因，例如 `image_preserved_after_ocr_timeout` |

注意：Markdown 是连续文本格式，渲染后没有原生分页；原始页码定位应使用 `metadata.pages`。PP-StructureV3 路线可提供较完整的页级行号和附件映射；Docling PDF 路线当前先提供 `page_count`，逐页行号可能为 `null`。

常见 `actual.reason`：

| reason | 说明 |
| --- | --- |
| `non_pdf_format` | 非 PDF，走 Docling/普通转换器 |
| `ocr_disabled` | OCR 关闭 |
| `requested_docling` | 调用方强制 Docling |
| `requested_ppstructure` | 调用方强制 PP-StructureV3 |
| `digital_pdf` | PDF 有文本层，走 Docling |
| `scanned_pdf_image_only` | 疑似纯图片扫描 PDF，走 PP-StructureV3 |
| `ppstructure_unavailable_fallback` | PP-StructureV3 未配置，auto 降级 Docling |
| `auto_docling_conservative` | 预检不足，保守走 Docling |

## 16. 图片和附件规则

- Docling 和 PP-StructureV3 输出的图片统一保存为附件。
- PP-StructureV3 返回的 base64/data URL 图片会保存到本地 `assets/`。
- PP-StructureV3 返回与 `PPSTRUCTURE_API_URL` 同源的 URL 图片会被下载并保存到本地 `assets/`。
- 其他来源 URL 图片不会下载，Markdown 保留原始引用，并在 `warnings` 中记录。
- 如果 PP 单页 OCR 超时且图片兜底开启，该页会作为图片附件保留。

## 17. 缓存规则

缓存按文件内容和转换参数隔离。不同 `ocr_mode` 或 `layout_engine` 不会互相命中。

调用方需要注意：

- 同一文件使用不同 OCR/layout 参数，可能得到同一个 `file_id`，但 `metadata.option_hash` 不同。
- 附件 URL 可能携带 `option_hash`，应使用返回值中的完整 URL。
- `cached=true` 表示命中已有转换结果。

## 18. 错误码

常见错误码：

| 错误码 | 说明 |
| --- | --- |
| `empty_file` | 上传文件为空 |
| `empty_filename` | 文件名为空 |
| `unsupported_file_format` | 文件格式不支持 |
| `file_too_large` | 文件超过上传大小限制 |
| `invalid_ocr_mode` | OCR 模式不合法 |
| `invalid_layout_engine` | 版面解析引擎不合法 |
| `conflicting_layout_options` | OCR 和 layout 参数冲突 |
| `upload_save_failed` | 上传文件保存失败 |
| `convert_failed` | 转换失败 |
| `convert_timeout` | 转换超时 |
| `ocr_model_missing` | RapidOCR 模型未配置或不完整 |
| `ppstructure_unavailable` | PP-StructureV3 服务未配置或不可用 |
| `ppstructure_failed` | PP-StructureV3 解析失败 |
| `ppstructure_timeout` | PP-StructureV3 调用超时 |
| `ppstructure_invalid_response` | PP-StructureV3 响应结构不合法 |
| `invalid_file_id` | 文件 ID 不合法 |
| `document_not_found` | 文档不存在 |
| `markdown_not_found` | Markdown 结果不存在 |
| `asset_not_found` | 附件不存在 |
| `invalid_task_id` | 任务 ID 不合法 |
| `task_not_found` | 任务不存在 |
| `unauthorized` | 未登录或会话无效 |

错误响应示例：

```json
{
  "detail": {
    "status": "failed",
    "status_text": "失败",
    "error_code": "conflicting_layout_options",
    "message": "ocr_mode=off时不能使用PP-StructureV3"
  }
}
```

## 19. 管理 API

以下接口要求登录，主要供 `/web` 管理页面使用，不建议业务系统强依赖：

- `POST /api/auth/login`
- `POST /api/auth/logout`
- `GET /api/auth/me`
- `GET /api/documents`
- `POST /api/documents/{file_id}/reconvert`
- `DELETE /api/documents/{file_id}/cache`
- `DELETE /api/documents/{file_id}`
- `GET /api/tasks`
- `POST /api/tasks/{task_id}/cancel`
- `POST /api/tasks/{task_id}/retry`

## 20. Python 调用示例

```python
import time
import requests

BASE_URL = "http://127.0.0.1:9527"


def convert_document(path: str, ocr_mode: str = "auto", layout_engine: str = "auto") -> dict:
    with open(path, "rb") as file_obj:
        response = requests.post(
            f"{BASE_URL}/api/tasks/convert",
            files={"file": file_obj},
            data={
                "ocr_mode": ocr_mode,
                "layout_engine": layout_engine,
            },
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


result = convert_document("scan.pdf", ocr_mode="auto", layout_engine="auto")
markdown = requests.get(f"{BASE_URL}{result['markdown_url']}", timeout=30).text
print(markdown[:500])
```

## 21. 配置项

常用 `.env`：

```env
DATA_DIR=./data
MAX_UPLOAD_SIZE_MB=100
API_PREFIX=/api
CONVERT_TIMEOUT_SECONDS=300
MAX_CONCURRENT_CONVERSIONS=2
TASK_WORKER_COUNT=1
OCR_DEFAULT_MODE=auto
LAYOUT_ENGINE_DEFAULT=auto
DOCLING_ARTIFACTS_PATH=./models/docling
RAPIDOCR_MODEL_PATH=./models/rapidocr
PPSTRUCTURE_API_URL=http://192.168.1.4:9528/layout-parsing
PPSTRUCTURE_TIMEOUT_SECONDS=300
PPSTRUCTURE_FULL_PARSE_TIMEOUT_SECONDS=120
PPSTRUCTURE_PAGE_RETRY_TIMEOUT_SECONDS=60
PPSTRUCTURE_PAGE_RETRY_MIN_PAGES=50
PPSTRUCTURE_PREPROCESS_RETRY_ENABLED=true
PPSTRUCTURE_PREPROCESS_THRESHOLD=185
PPSTRUCTURE_PAGE_IMAGE_FALLBACK_ENABLED=true
PPSTRUCTURE_PAGE_IMAGE_FALLBACK_MAX_SIDE=1800
PPSTRUCTURE_RENDER_SCALE=1.5
PPSTRUCTURE_USE_TABLE_RECOGNITION=true
PPSTRUCTURE_USE_SEAL_RECOGNITION=true
```

## 22. OpenAPI

OpenAPI JSON：

```text
docs/DocumentToMarkdown_v1.2_openapi.json
```

运行服务后也可以访问：

```text
http://127.0.0.1:9527/docs
http://127.0.0.1:9527/redoc
http://127.0.0.1:9527/openapi.json
```

可导入 Apifox、Postman、Swagger UI 或 OpenAPI Generator。
