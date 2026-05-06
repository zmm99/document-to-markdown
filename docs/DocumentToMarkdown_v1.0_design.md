# DocumentToMarkdown v1.0 设计文档

## 1. 版本目标

v1.0 实现一个轻量同步版文档转 Markdown 服务，为 AI 知识库导入提供基础支撑。

本版本重点解决：

- 通过 API 上传文件并转换为 Markdown。
- 使用本地目录保存原始文件、Markdown 结果、metadata 和图片附件。
- 使用 SQLite 记录上传和解析结果。
- 使用文件 md5 作为文件 ID。
- 相同 md5 和文件格式已有成功解析结果时，直接返回缓存结果。
- 提供删除解析缓存接口，用于解析策略升级后强制重新解析。
- 支持常见数字文档基础转换。

本版本不实现：

- OCR 识别。
- 扫描 PDF 解析。
- 任务队列。
- 对象存储。
- AI 内容修复。
- 用户体系和权限控制。

## 2. 支持格式

v1.0 支持以下数字文档格式：

| 文件类型 | 扩展名 | 处理方式 |
| --- | --- | --- |
| PDF | `.pdf` | 使用 Docling 转换，仅支持可复制文字的 PDF |
| Word | `.docx` | 使用 Docling 转换 |
| PowerPoint | `.pptx` | 使用 Docling 转换 |
| Excel | `.xlsx` | 使用 openpyxl 自定义转 Markdown 表格 |
| CSV | `.csv` | 使用 Python 标准库自定义转 Markdown 表格 |
| HTML | `.html`, `.htm` | 使用 BeautifulSoup 或 Pandoc 转换 |
| 文本 | `.txt` | 直接转 Markdown 文本 |
| Markdown | `.md`, `.markdown` | 直接保存并返回 |

暂不支持以下格式：

| 文件类型 | 原因 |
| --- | --- |
| 扫描 PDF | 需要 OCR，放入后续版本 |
| 图片文件 | 本质是 OCR，放入后续版本 |
| `.doc`, `.xls`, `.ppt` | 老 Office 格式依赖 LibreOffice，放入后续版本 |
| `.wps`, `.ofd` | 格式处理复杂，后续单独评估 |

## 3. 技术选型

| 模块 | 选型 |
| --- | --- |
| API 服务 | FastAPI |
| 数据库 | SQLite |
| 文件存储 | 本地目录 |
| PDF/DOCX/PPTX 转换 | Docling，作为 v1.0 必选依赖 |
| XLSX 转换 | openpyxl |
| CSV 转换 | Python csv 标准库 |
| HTML 转换 | BeautifulSoup 或 Pandoc |
| 配置管理 | `.env` + Pydantic Settings |

## 4. 存储目录

文件统一存储在项目 `data` 目录下。

```text
data/
  uploads/
    yyyyMMdd/
      {md5}.{ext}

  outputs/
    yyyyMMdd/
      {md5}/
        result.md
        metadata.json
        assets/

  document_to_markdown.db
```

说明：

- `yyyyMMdd` 为上传当天日期，例如 `20250101`。
- `file_id` 等于文件 md5 去除 `-` 后的值。
- 标准 md5 本身不包含 `-`，仍统一执行去除逻辑。
- API 不直接暴露磁盘路径，只返回访问 URL。

## 5. 核心流程

```text
1. 客户端上传文件
2. 服务端校验文件大小和扩展名
3. 计算文件 md5，得到 file_id
4. 识别文件格式 file_format
5. 查询 SQLite
   - 条件：md5 + file_format + status = success
6. 如果命中缓存
   - 读取已有 markdown、metadata、assets
   - 返回 cached = true
7. 如果未命中缓存
   - 创建 uploads/yyyyMMdd/ 目录
   - 保存原始文件为 uploads/yyyyMMdd/{md5}.{ext}
   - 创建 outputs/yyyyMMdd/{md5}/ 目录
   - 调用对应转换器生成 result.md、metadata.json、assets/
   - 写入 SQLite 记录
   - 返回 cached = false
```

## 6. API 设计

### 6.1 上传并转换

```http
POST /api/documents/convert
Content-Type: multipart/form-data
```

请求字段：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| file | file | 是 | 上传的文档文件 |

成功响应：

```json
{
  "file_id": "d41d8cd98f00b204e9800998ecf8427e",
  "cached": false,
  "status": "success",
  "file_format": "pdf",
  "markdown_url": "/api/documents/d41d8cd98f00b204e9800998ecf8427e/markdown",
  "assets": [
    {
      "name": "page-1-image-1.png",
      "content_type": "image/png",
      "url": "/api/documents/d41d8cd98f00b204e9800998ecf8427e/assets/page-1-image-1.png"
    }
  ],
  "metadata": {
    "original_filename": "demo.pdf",
    "file_size": 1024,
    "engine": "docling"
  },
  "warnings": []
}
```

失败响应：

```json
{
  "file_id": "d41d8cd98f00b204e9800998ecf8427e",
  "status": "failed",
  "error_code": "convert_failed",
  "message": "文档转换失败"
}
```

不支持格式响应：

```json
{
  "status": "unsupported",
  "error_code": "unsupported_file_format",
  "message": "当前版本不支持该文件格式"
}
```

### 6.2 获取文档信息

```http
GET /api/documents/{file_id}
```

返回文档基本信息、解析状态、Markdown URL、附件列表和 metadata。

### 6.3 获取 Markdown

```http
GET /api/documents/{file_id}/markdown
```

响应：

```http
Content-Type: text/markdown; charset=utf-8
```

返回 `result.md` 内容。

Markdown 中的图片链接使用 API 地址：

```markdown
![图片](/api/documents/{file_id}/assets/page-1-image-1.png)
```

### 6.4 获取图片附件

```http
GET /api/documents/{file_id}/assets/{asset_name}
```

通过 SQLite 查询附件路径，使用文件响应返回图片内容。

### 6.5 下载完整结果

```http
GET /api/documents/{file_id}/download
```

返回 zip 文件，包含：

```text
result.md
metadata.json
assets/
```

### 6.6 删除解析缓存

```http
DELETE /api/documents/{file_id}/cache
```

用途：

- 删除指定文件的解析缓存。
- 删除该文件对应的 `parse_records` 和 `document_assets` 记录。
- 删除该文件对应的 `outputs/yyyyMMdd/{md5}/` 输出目录。
- 保留 `documents` 上传记录和 `uploads/yyyyMMdd/{md5}.{ext}` 原始文件。
- 下次上传相同 md5 和文件格式时，因为没有成功解析记录，会重新执行解析逻辑。

成功响应：

```json
{
  "file_id": "d41d8cd98f00b204e9800998ecf8427e",
  "status": "success",
  "deleted_parse_records": 1,
  "deleted_assets": 2,
  "deleted_output_dirs": 1
}
```

说明：

- 如果手动删除 `parse_records` 中该文件的成功解析记录，也可以达到下次重新解析的效果。
- 推荐优先使用 API 删除解析缓存，API 会同步清理附件记录和输出目录。

## 7. 数据库设计

### 7.1 documents

保存文件上传记录。

```sql
CREATE TABLE documents (
    id TEXT PRIMARY KEY,
    md5 TEXT NOT NULL,
    original_filename TEXT NOT NULL,
    file_format TEXT NOT NULL,
    mime_type TEXT,
    file_size INTEGER NOT NULL,
    storage_date TEXT NOT NULL,
    upload_path TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(md5, file_format)
);
```

### 7.2 parse_records

保存文档解析记录。

```sql
CREATE TABLE parse_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id TEXT NOT NULL,
    file_format TEXT NOT NULL,
    engine TEXT NOT NULL,
    engine_version TEXT,
    status TEXT NOT NULL,
    output_dir TEXT,
    markdown_path TEXT,
    metadata_path TEXT,
    error_code TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(document_id) REFERENCES documents(id)
);
```

### 7.3 document_assets

保存转换结果中的图片附件。

```sql
CREATE TABLE document_assets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id TEXT NOT NULL,
    asset_name TEXT NOT NULL,
    content_type TEXT,
    asset_path TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(document_id, asset_name),
    FOREIGN KEY(document_id) REFERENCES documents(id)
);
```

## 8. 转换器设计

转换器保持简单接口：

```python
class ConvertResult:
    markdown: str
    metadata: dict
    assets: list
    warnings: list


class Converter:
    def convert(self, input_path: Path, output_dir: Path) -> ConvertResult:
        ...
```

v1.0 内置转换器：

| 转换器 | 支持格式 |
| --- | --- |
| PdfConverter | `.pdf` |
| DocxConverter | `.docx` |
| PptxConverter | `.pptx` |
| XlsxConverter | `.xlsx` |
| CsvConverter | `.csv` |
| HtmlConverter | `.html`, `.htm` |
| TxtConverter | `.txt` |
| MarkdownConverter | `.md`, `.markdown` |

选择规则：

```text
根据 file_format 查找转换器。
未找到转换器则返回 unsupported_file_format。
转换失败则记录 parse_records.status = failed。
```

## 9. 输入校验

v1.0 必须校验：

- 文件不能为空。
- 文件名不能为空。
- 文件扩展名必须在支持列表内。
- 文件大小不能超过配置限制。
- `file_id` 必须为 32 位十六进制字符串。
- `asset_name` 只能是单个文件名，不能包含路径分隔符。

默认文件大小限制：

```text
MAX_UPLOAD_SIZE_MB = 100
```

## 10. 配置项

```text
APP_NAME=DocumentToMarkdown
DATA_DIR=./data
MAX_UPLOAD_SIZE_MB=100
API_PREFIX=/api
```

## 11. 错误码

| 错误码 | 说明 |
| --- | --- |
| `empty_file` | 上传文件为空 |
| `file_too_large` | 文件超过大小限制 |
| `unsupported_file_format` | 不支持的文件格式 |
| `invalid_file_id` | 文件 ID 格式错误 |
| `document_not_found` | 文档不存在 |
| `markdown_not_found` | Markdown 结果不存在 |
| `asset_not_found` | 附件不存在 |
| `convert_failed` | 转换失败 |

## 12. 后续版本规划

v1.1 可考虑：

- 扫描 PDF 检测。
- 图片 OCR。
- PaddleOCR 接入。
- 老 Office 格式通过 LibreOffice 转换。

v1.2 可考虑：

- 表格结构增强。
- PDF 版面修复。
- Markdown 清洗和标题层级修复。
- 知识库 chunk 输出。

v2.0 可考虑：

- 异步任务队列。
- 对象存储。
- 多实例部署。
- 用户权限。
