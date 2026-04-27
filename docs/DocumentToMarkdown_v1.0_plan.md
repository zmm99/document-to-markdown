# DocumentToMarkdown v1.0 开发计划

## 1. 开发目标

按照 `DocumentToMarkdown_v1.0_design.md` 实现轻量同步版文档转 Markdown 服务。

本版本交付内容：

- FastAPI API 服务。
- 本地 `data/uploads/yyyyMMdd/` 和 `data/outputs/yyyyMMdd/` 文件存储。
- SQLite 上传记录、解析记录和附件记录。
- md5 作为 `file_id`。
- `md5 + file_format + success` 缓存命中直接返回结果。
- 删除解析缓存接口，支持后续解析策略升级后重新解析存量文件。
- 基础数字文档转换：PDF、DOCX、PPTX、XLSX、CSV、HTML、TXT、MD。
- Markdown、图片附件和完整 zip 结果获取接口。

## 2. 开发原则

- 只实现 v1.0 设计文档中的能力。
- 不实现 OCR、任务队列、对象存储、用户权限。
- 接口输入严格校验。
- 代码保持简单，避免过度封装。
- 每完成一个阶段做一次可运行检查。

## 3. 阶段计划

### 阶段 1：项目初始化

任务：

- 创建 Python 项目结构。
- 创建依赖文件。
- 创建基础配置。
- 创建 FastAPI 应用入口。
- 创建健康检查接口。

建议目录：

```text
app/
  main.py
  config.py
  api/
  core/
  converters/
  db/
tests/
data/
```

主要文件：

- `pyproject.toml`
- `.env.example`
- `app/main.py`
- `app/config.py`

验收标准：

- 可以启动 FastAPI 服务。
- `GET /health` 返回正常状态。

### 阶段 2：数据库初始化

任务：

- 使用 SQLite 创建数据库。
- 实现 `documents` 表。
- 实现 `parse_records` 表。
- 实现 `document_assets` 表。
- 实现基础数据库连接和初始化逻辑。

主要文件：

- `app/db/database.py`
- `app/db/schema.sql`
- `app/db/repository.py`

验收标准：

- 服务启动时可以创建 `data/document_to_markdown.db`。
- 三张表结构与设计文档一致。

### 阶段 3：文件校验与本地存储

任务：

- 实现上传文件扩展名校验。
- 实现文件大小校验。
- 实现 md5 计算。
- 实现 `yyyyMMdd` 日期目录创建。
- 保存上传文件到 `data/uploads/yyyyMMdd/{md5}.{ext}`。
- 创建输出目录 `data/outputs/yyyyMMdd/{md5}/`。

主要文件：

- `app/core/file_utils.py`
- `app/core/storage.py`

验收标准：

- 上传同一文件得到相同 `file_id`。
- 文件按日期目录保存。
- 不支持格式会返回 `unsupported_file_format`。
- 超出大小限制会返回 `file_too_large`。

### 阶段 4：转换器基础实现

任务：

- 定义简单的转换结果结构。
- 实现转换器选择逻辑。
- 实现 TXT 转换器。
- 实现 MD 转换器。
- 实现 CSV 转换器。
- 实现 XLSX 转换器。
- 实现 HTML 转换器。
- 实现 PDF、DOCX、PPTX 转换器。

主要文件：

- `app/converters/base.py`
- `app/converters/registry.py`
- `app/converters/text.py`
- `app/converters/markdown.py`
- `app/converters/csv_converter.py`
- `app/converters/xlsx.py`
- `app/converters/html.py`
- `app/converters/docling_converter.py`

验收标准：

- 每种支持格式都能生成 `result.md`。
- 转换结果能生成 `metadata.json`。
- 转换失败时写入失败解析记录。

### 阶段 5：转换 API

任务：

- 实现 `POST /api/documents/convert`。
- 查询缓存记录。
- 缓存命中时返回已有结果。
- 缓存未命中时保存文件、执行转换、写入数据库。
- 返回 Markdown URL、附件 URL、metadata 和 warnings。
- 实现 `DELETE /api/documents/{file_id}/cache`。
- 删除解析缓存时清理解析记录、附件记录和输出目录，保留原始上传文件。

主要文件：

- `app/api/documents.py`
- `app/core/document_service.py`

验收标准：

- 首次上传返回 `cached = false`。
- 重复上传相同文件和格式返回 `cached = true`。
- SQLite 中有对应上传和解析记录。
- 删除解析缓存后，再次上传相同文件会重新解析。

### 阶段 6：结果获取 API

任务：

- 实现 `GET /api/documents/{file_id}`。
- 实现 `GET /api/documents/{file_id}/markdown`。
- 实现 `GET /api/documents/{file_id}/assets/{asset_name}`。
- 实现 `GET /api/documents/{file_id}/download`。
- 校验 `file_id` 和 `asset_name`。

主要文件：

- `app/api/documents.py`
- `app/core/archive.py`

验收标准：

- 可以通过 API 获取 Markdown 内容。
- 可以通过 API 获取图片附件。
- 可以下载包含 `result.md`、`metadata.json`、`assets/` 的 zip。
- 不存在的文档或附件返回明确错误码。

### 阶段 7：测试

任务：

- 添加单元测试。
- 添加 API 测试。
- 准备最小样例文件。
- 验证缓存命中逻辑。
- 验证输入校验。

建议测试范围：

- TXT 转换。
- MD 转换。
- CSV 转换。
- XLSX 转换。
- HTML 转换。
- 重复上传缓存命中。
- 删除解析缓存。
- 不支持扩展名。
- 非法 `file_id`。
- 非法 `asset_name`。

主要文件：

- `tests/test_api_documents.py`
- `tests/test_converters.py`
- `tests/fixtures/`

验收标准：

- 测试全部通过。
- 手动上传样例文件可以获得 Markdown。

### 阶段 8：代码审查

检查项：

- 是否严格按照设计文档实现。
- 是否存在过度封装。
- 是否存在未校验的 API 输入。
- 是否存在真实磁盘路径泄露。
- 是否存在路径穿越风险。
- 是否正确记录失败解析结果。
- 是否没有实现 v1.0 之外的功能。

验收标准：

- 完成代码审查问题修复。
- 保留必要的简单注释，删除无意义注释。

### 阶段 9：测试版本发布

任务：

- 补充 README 启动说明。
- 补充 `.env.example`。
- 确认依赖安装命令。
- 确认启动命令。
- 使用样例文件完成手动测试。

验收标准：

- 可以从空环境按 README 启动服务。
- 可以完成上传、转换、获取 Markdown、获取附件、下载 zip。

### 阶段 10：正式版本发布

任务：

- 确认 v1.0 功能清单。
- 确认已知限制。
- 确认后续版本规划。
- 标记正式版本。

验收标准：

- v1.0 代码、文档和测试结果齐备。
- 已知限制清晰记录。

## 4. 推荐实施顺序

```text
阶段 1 -> 阶段 2 -> 阶段 3 -> 阶段 4 -> 阶段 5 -> 阶段 6 -> 阶段 7 -> 阶段 8 -> 阶段 9 -> 阶段 10
```

优先完成 TXT、MD、CSV、XLSX、HTML 转换，再接入 PDF、DOCX、PPTX。这样可以先验证完整 API、存储和缓存链路，再处理更复杂的转换引擎。

## 5. v1.0 完成标准

- `POST /api/documents/convert` 可用。
- `DELETE /api/documents/{file_id}/cache` 可用。
- `GET /api/documents/{file_id}` 可用。
- `GET /api/documents/{file_id}/markdown` 可用。
- `GET /api/documents/{file_id}/assets/{asset_name}` 可用。
- `GET /api/documents/{file_id}/download` 可用。
- 支持 PDF、DOCX、PPTX、XLSX、CSV、HTML、TXT、MD。
- 同 md5 和文件格式成功解析后再次上传会直接返回缓存。
- 删除解析缓存后，同 md5 和文件格式再次上传会重新解析。
- 上传文件和输出结果都按 `yyyyMMdd` 日期目录存储。
- SQLite 正确记录上传、解析和附件。
- 不支持 OCR 和扫描件，并返回明确错误。
