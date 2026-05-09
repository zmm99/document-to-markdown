# DocumentToMarkdown v1.0 接口文档

## 1. 服务地址

默认本地服务地址：

```text
http://127.0.0.1:8000
```

启动命令：

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

接口文档：

```text
http://127.0.0.1:8000/docs
```

健康检查：

```http
GET /health
```

响应：

```json
{
  "status": "ok"
}
```

## 2. 通用规则

### 2.1 API 前缀

v1.0 默认 API 前缀：

```text
/api
```

文档中的业务接口均以 `/api` 开头。

### 2.2 认证

v1.0 不实现用户体系和权限控制，不需要认证参数。

### 2.3 支持格式

| 文件类型 | 扩展名 | 转换方式 |
| --- | --- | --- |
| PDF | `.pdf` | Docling，仅支持可复制文字的 PDF |
| Word | `.docx` | Docling |
| PowerPoint | `.pptx` | Docling |
| Excel | `.xlsx` | openpyxl |
| CSV | `.csv` | Python csv |
| HTML | `.html`, `.htm` | BeautifulSoup |
| 文本 | `.txt` | 直接读取文本 |
| Markdown | `.md`, `.markdown` | 直接读取 Markdown |

暂不支持 OCR、扫描 PDF、图片文件和老 Office 格式。

### 2.4 file_id

`file_id` 为服务端生成的雪花 ID 字符串。md5 仅用于服务端内部缓存查询，不再作为对外 ID。

示例：

```text
313654404807069696
```

### 2.5 错误响应

错误响应统一放在 `detail` 字段中：

```json
{
  "detail": {
    "status": "failed",
    "error_code": "document_not_found",
    "message": "document not found"
  }
}
```

不支持格式时 `status` 为 `unsupported`：

```json
{
  "detail": {
    "status": "unsupported",
    "error_code": "unsupported_file_format",
    "message": "unsupported file format"
  }
}
```

## 3. 上传并转换

```http
POST /api/documents/convert
Content-Type: multipart/form-data
```

请求字段：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| file | file | 是 | 待转换文档 |

成功响应：

```json
{
  "file_id": "313654404807069696",
  "status": "success",
  "file_format": "txt",
  "markdown_url": "/api/documents/313654404807069696/markdown",
  "assets": [],
  "metadata": {
    "engine": "text",
    "source_format": "txt"
  },
  "warnings": [],
  "cached": false
}
```

字段说明：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| file_id | string | 服务端生成的不透明文件 ID |
| status | string | 成功时为 `success` |
| file_format | string | 识别后的文件格式 |
| markdown_url | string | Markdown 获取地址 |
| assets | array | 图片附件列表 |
| metadata | object | 转换器返回的元数据 |
| warnings | array | 转换警告 |
| cached | boolean | 是否命中已有成功解析缓存 |

缓存规则：

- 服务按 `md5 + file_format + success` 查询缓存。
- 命中缓存时不重新转换，返回 `cached: true`。
- 删除解析缓存后，再次上传同一文件会重新转换。

curl 示例：

```bash
curl -X POST "http://127.0.0.1:8000/api/documents/convert" \
  -F "file=@demo.txt"
```

PowerShell 示例：

```powershell
curl.exe -X POST "http://127.0.0.1:8000/api/documents/convert" -F "file=@demo.txt"
```

## 4. 获取文档信息

```http
GET /api/documents/{file_id}
```

路径参数：

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| file_id | 是 | 服务端生成的文件 ID，旧 32 位 md5 ID 暂时兼容 |

成功响应：

```json
{
  "file_id": "313654404807069696",
  "status": "success",
  "file_format": "txt",
  "markdown_url": "/api/documents/313654404807069696/markdown",
  "assets": [],
  "metadata": {
    "engine": "text",
    "source_format": "txt"
  },
  "warnings": []
}
```

如果最近一次解析失败，响应示例：

```json
{
  "file_id": "313654404807069696",
  "status": "failed",
  "file_format": "pdf",
  "error_code": "convert_failed",
  "message": "document conversion failed"
}
```

## 5. 获取 Markdown

```http
GET /api/documents/{file_id}/markdown
```

成功响应：

```http
Content-Type: text/markdown; charset=utf-8
```

响应体为 Markdown 文本。

示例：

```bash
curl "http://127.0.0.1:8000/api/documents/313654404807069696/markdown"
```

## 6. 获取附件

```http
GET /api/documents/{file_id}/assets/{asset_name}
```

路径参数：

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| file_id | 是 | 服务端生成的文件 ID，旧 32 位 md5 ID 暂时兼容 |
| asset_name | 是 | 单个附件文件名，不能包含路径分隔符 |

成功响应：

- 返回附件文件内容。
- `Content-Type` 优先使用数据库记录的附件类型。

附件响应字段示例来自转换接口或文档信息接口：

```json
{
  "name": "page-1-image-1.png",
  "content_type": "image/png",
  "url": "/api/documents/313654404807069696/assets/page-1-image-1.png"
}
```

## 7. 下载完整结果

```http
GET /api/documents/{file_id}/download
```

成功响应：

```http
Content-Type: application/zip
Content-Disposition: attachment; filename="{file_id}.zip"
```

zip 内容：

```text
result.md
metadata.json
assets/
```

说明：

- `assets/` 目录仅在存在附件时包含文件。
- 如果没有附件，zip 中通常只包含 `result.md` 和 `metadata.json`。

示例：

```bash
curl -o result.zip "http://127.0.0.1:8000/api/documents/313654404807069696/download"
```

## 8. 删除解析缓存

```http
DELETE /api/documents/{file_id}/cache
```

用途：

- 删除指定文件的解析记录。
- 删除指定文件的附件记录。
- 删除对应输出目录。
- 保留上传文件记录和原始上传文件。

成功响应：

```json
{
  "file_id": "313654404807069696",
  "status": "success",
  "deleted_parse_records": 1,
  "deleted_assets": 0,
  "deleted_output_dirs": 1,
  "warnings": []
}
```

删除后再次上传相同 md5 和格式的文件，会重新执行转换。

## 9. 错误码

| HTTP 状态码 | error_code | 说明 |
| --- | --- | --- |
| 400 | `empty_file` | 上传文件为空或缺少文件 |
| 400 | `file_too_large` | 文件超过配置限制 |
| 400 | `unsupported_file_format` | 不支持的文件格式 |
| 400 | `invalid_file_id` | `file_id` 格式错误 |
| 404 | `document_not_found` | 文档不存在 |
| 404 | `markdown_not_found` | Markdown 结果不存在 |
| 404 | `asset_not_found` | 附件不存在或附件名非法 |
| 500 | `convert_failed` | 文档转换失败 |
| 500 | `convert_timeout` | 文档转换超时 |
| 500 | `converter_dependency_missing` | 转换依赖缺失 |

## 10. 调用流程示例

```text
1. POST /api/documents/convert 上传文件
2. 从响应中读取 file_id、markdown_url、assets、cached
3. GET markdown_url 获取 Markdown
4. 如有附件，按 assets[].url 获取附件
5. 如需完整结果，GET /api/documents/{file_id}/download 下载 zip
6. 如需强制重转，DELETE /api/documents/{file_id}/cache 后重新上传
```
