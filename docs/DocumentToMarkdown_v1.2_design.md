# DocumentToMarkdown v1.2 设计文档

## 1. 设计目标

v1.2 增加自动 OCR 和复杂扫描版面解析能力，同时保持 v1.1 已有 API、任务、附件和部署方式兼容。

设计目标：

- 对外参数保持简单，只暴露 `ocr_mode` 和 `layout_engine`。
- Docling 继续作为默认解析路线。
- RapidOCR 作为 Docling 路线内置 OCR 能力，不作为 API 参数暴露。
- PP-StructureV3 作为独立服务接入，定位为复杂版面解析后端，不是普通 OCR 引擎。
- 所有结果归一到当前 `ConvertResult`、`result.md`、`metadata.json`、`assets/`。
- 模型文件外置挂载，镜像不内置大模型。

## 2. 当前代码评估

### 2.1 Docling 转换器

当前 `app/converters/docling_converter.py` 对 PDF 的配置为：

```python
pipeline_options = PdfPipelineOptions()
pipeline_options.do_ocr = False
pipeline_options.do_table_structure = False
pipeline_options.generate_page_images = True
pipeline_options.generate_picture_images = True
pipeline_options.images_scale = 2.0
```

当前行为：

- PDF OCR 显式关闭。
- 表格结构识别关闭。
- 页面图片和文档图片会生成。
- Markdown 导出使用 `ImageRefMode.REFERENCED`。
- 图片附件会保存到 `assets/`，并改写成 `/api/documents/{file_id}/assets/{asset_name}`。

v1.2 必须保留图片附件导出逻辑。

### 2.2 转换隔离

当前转换由 `app/core/conversion_runner.py` 启动子进程执行：

```text
API / task worker
  -> run_converter_with_timeout()
  -> python -m app.core.conversion_worker
  -> get_converter(file_format).convert()
```

已有能力：

- 转换超时。
- 转换并发限制。
- 子进程隔离。

v1.2 需要把 `ocr_mode`、`layout_engine` 和内部选择结果传入转换链路。

### 2.3 缓存现状

当前缓存按 `md5 + file_format` 查询成功结果。加入 OCR 和 PP-StructureV3 后，这会导致错误命中。

v1.2 必须增加转换选项指纹：

```text
option_hash = hash(file_format + ocr_mode + requested_layout_engine + actual_layout_engine + model_config)
```

历史 v1.1 缓存按：

```text
ocr_mode=off
layout_engine=docling
```

兼容处理。

## 3. 总体架构

```text
POST /api/documents/convert
POST /api/tasks/convert
        |
        v
解析 ConversionOptions
        |
        v
自动路由决策
        |
        +-- layout_engine=docling
        |      |
        |      v
        |   Docling + RapidOCR
        |      |
        |      v
        |   ConvertResult
        |
        +-- layout_engine=ppstructure
               |
               v
            PP-StructureV3 HTTP 服务
               |
               v
            PPStructureAdapter
               |
               v
            ConvertResult
        |
        v
write_convert_result()
        |
        v
result.md + metadata.json + assets/
```

## 4. 转换参数模型

建议新增：

```text
app/core/conversion_options.py
```

核心模型：

```python
@dataclass(frozen=True)
class ConversionOptions:
    ocr_mode: str
    layout_engine: str
    option_hash: str
```

枚举：

```text
ocr_mode: off | auto | full
layout_engine: docling | ppstructure | auto
```

默认值来自配置：

```env
OCR_DEFAULT_MODE=auto
LAYOUT_ENGINE_DEFAULT=auto
```

校验规则：

- `ocr_mode` 只能为 `off`、`auto`、`full`。
- `layout_engine` 只能为 `docling`、`ppstructure`、`auto`。
- `ocr_mode=off&layout_engine=ppstructure` 返回 400。

## 5. 自动路由设计

建议新增：

```text
app/core/layout_router.py
```

输入：

- 文件格式。
- 文件路径。
- `ocr_mode`。
- `layout_engine`。
- 可选 PDF 预检结果。

输出：

```python
@dataclass(frozen=True)
class LayoutDecision:
    actual_layout_engine: str
    ocr_applied: bool
    reason: str
    warnings: list[str]
```

第一阶段规则：

| 条件 | 选择 | reason |
| --- | --- | --- |
| 非 PDF | `docling` | `non_pdf_format` |
| `ocr_mode=off` | `docling` | `ocr_disabled` |
| 用户指定 `layout_engine=docling` | `docling` | `requested_docling` |
| 用户指定 `layout_engine=ppstructure` | `ppstructure` | `requested_ppstructure` |
| PDF 有文本层且版式不复杂 | `docling` | `digital_pdf` |
| PDF 疑似纯图片扫描件且 PP-StructureV3 已配置 | `ppstructure` | `scanned_pdf_image_only` |
| PP-StructureV3 不可用且允许自动降级 | `docling` | `ppstructure_unavailable_fallback` |
| PDF 预检信号不足 | `docling` | `auto_docling_conservative` |

第一阶段 PDF 预检保持轻量，不引入额外 PDF 解析依赖：

- 通过 `/Font`、`/ToUnicode` 等 PDF token 粗略判断是否有文本层。
- 通过 `/Subtype /Image` 粗略判断是否包含位图图片。
- 当存在位图图片且未发现文本层时，按疑似纯图片扫描件处理。

说明：

- 裸 `BT` token 可能只表示 PDF 内容流文本操作符，不足以证明存在可用字体或文本层，因此第一阶段不把裸 `BT` 作为文本层依据。
- 轻量预检只读取文件前部固定字节，可能对极端 PDF 判断不准；调用方仍可通过 `layout_engine=docling|ppstructure` 手工指定路线。

表格线条、印章颜色区域、扫描页复杂度判断后续增强；当前如果复杂度判断不可靠，仍允许先保守走 Docling + RapidOCR，并通过手工参数 `layout_engine=ppstructure` 强制使用 PP-StructureV3。

## 6. Docling 路线设计

Docling 仍由 `DoclingConverter` 负责。

### 6.1 OCR 配置

`ocr_mode=off`：

```python
pipeline_options.do_ocr = False
```

`ocr_mode=auto`：

```python
pipeline_options.do_ocr = True
pipeline_options.ocr_options = RapidOcrOptions(
    force_full_page_ocr=False,
)
```

`ocr_mode=full`：

```python
pipeline_options.do_ocr = True
pipeline_options.ocr_options = RapidOcrOptions(
    force_full_page_ocr=True,
)
```

说明：

- RapidOCR 是 Docling 路线的内部默认 OCR。
- 不通过 API 暴露 `ocr_engine`。
- 后续可用服务端配置切换 Docling OCR 后端，但不影响 v1.2 对外接口。

### 6.2 图片保留

继续保留：

```python
pipeline_options.generate_page_images = True
pipeline_options.generate_picture_images = True
pipeline_options.images_scale = 2.0
```

Markdown 导出继续使用：

```python
document.save_as_markdown(
    markdown_path,
    artifacts_dir=Path("assets"),
    image_mode=ImageRefMode.REFERENCED,
)
```

## 7. PP-StructureV3 路线设计

建议新增：

```text
app/converters/ppstructure_converter.py
app/core/ppstructure_client.py
app/core/ppstructure_adapter.py
```

职责：

- `ppstructure_client.py`：调用 PP-StructureV3 HTTP 服务。
- `ppstructure_adapter.py`：把 PP-StructureV3 响应转换为 `ConvertResult`。
- `ppstructure_converter.py`：实现统一 converter 接口。

### 7.1 请求方式

PP-StructureV3 服务接口：

```http
POST /layout-parsing
Content-Type: application/json
```

第一阶段建议使用 base64 方式，降低服务间文件访问复杂度：

```json
{
  "file": "<base64>",
  "fileType": 0,
  "useSealRecognition": true,
  "useTableRecognition": true,
  "returnMarkdownImages": true,
  "visualize": false
}
```

说明：

- base64 会增加内存和网络传输，适合第一阶段跑通功能。
- 后续如遇到大 PDF 性能问题，再增加内部 URL 或共享目录传输方式。
- 不把传输方式暴露给外部调用方。

### 7.2 响应结构

PP-StructureV3 响应中的关键字段：

```json
{
  "result": {
    "layoutParsingResults": [
      {
        "markdown": {
          "text": "...",
          "images": {
            "imgs/table_1.jpg": "<base64>"
          },
          "isStart": true,
          "isEnd": true
        },
        "prunedResult": {},
        "outputImages": {},
        "inputImage": null,
        "exports": null
      }
    ],
    "dataInfo": {}
  }
}
```

### 7.3 输出归一

转换流程：

```text
1. 遍历 layoutParsingResults
2. 按页顺序读取 markdown.text
3. 收集 markdown.images
4. 将 base64 图片解码保存到 assets/
5. 将图片统一命名为 image-001.png / image-002.jpg
6. 替换 Markdown 中原始图片路径为当前附件 URL
7. 合并多页 Markdown 为 result.md
8. 将 prunedResult 和服务信息写入 metadata.json
```

最终返回：

```python
ConvertResult(
    markdown=merged_markdown,
    metadata={
        "engine": "ppstructure",
        "layout_engine": "ppstructure",
        "ocr_applied": True,
        ...
    },
    assets=[...],
)
```

## 8. PP-StructureV3 页数配置

PP-StructureV3 服务应关闭默认 10 页限制。

建议服务配置：

```yaml
Serving:
  extra:
    max_num_input_imgs: 300
```

如果服务资源允许且 PP-StructureV3 部署方式支持，也可以设置为 `null`，表示不在服务层限制输入页数。

主服务仍保留：

- `MAX_UPLOAD_SIZE_MB`
- `CONVERT_TIMEOUT_SECONDS`
- `MAX_CONCURRENT_CONVERSIONS`
- `PPSTRUCTURE_TIMEOUT_SECONDS`
- `PPSTRUCTURE_FULL_PARSE_TIMEOUT_SECONDS`
- `PPSTRUCTURE_PAGE_RETRY_TIMEOUT_SECONDS`
- `PPSTRUCTURE_PAGE_RETRY_MIN_PAGES`
- `PPSTRUCTURE_PREPROCESS_RETRY_ENABLED`
- `PPSTRUCTURE_PAGE_IMAGE_FALLBACK_ENABLED`

避免超大扫描件无限占用资源。

### 8.1 大文档和慢页兜底

第一阶段 PP-StructureV3 转换器内置以下兜底策略：

```text
PDF 页数 >= PPSTRUCTURE_PAGE_RETRY_MIN_PAGES
  -> 直接按页渲染并逐页调用 PP-StructureV3

整份调用超过 PPSTRUCTURE_FULL_PARSE_TIMEOUT_SECONDS
  -> 自动切换为按页调用

单页调用超过 PPSTRUCTURE_PAGE_RETRY_TIMEOUT_SECONDS
  -> 渲染该页，黑白阈值预处理后重试

预处理后仍超时
  -> 将该页作为 JPEG 图片附件保留，并在 Markdown 中引用
```

兜底目标：

- 避免大扫描 PDF 因单个复杂页导致整份任务失败。
- 对地图、规划图、照片类页面，不强制 OCR 成文字，优先保留图片附件。
- 在 metadata 中记录哪些页被预处理、哪些页被图片保留，便于后续人工复核。

## 9. 数据库设计

### 9.1 parse_records

新增：

```sql
ALTER TABLE parse_records ADD COLUMN option_hash TEXT;
ALTER TABLE parse_records ADD COLUMN options_json TEXT;
```

用途：

- 记录转换参数。
- 参与缓存判断。
- 支持排查具体解析路线。

### 9.2 conversion_tasks

新增：

```sql
ALTER TABLE conversion_tasks ADD COLUMN option_hash TEXT;
ALTER TABLE conversion_tasks ADD COLUMN options_json TEXT;
```

用途：

- 异步任务创建后保留参数。
- worker 执行时使用创建任务时的参数。
- 重试任务继承原任务参数。

### 9.3 schema migration

当前 `init_db()` 只执行 `CREATE TABLE IF NOT EXISTS`，不会给旧表补字段。

v1.2 需要增加轻量迁移：

```text
run_schema_migrations(conn)
  -> PRAGMA table_info(parse_records)
  -> 缺字段则 ALTER TABLE
  -> PRAGMA table_info(conversion_tasks)
  -> 缺字段则 ALTER TABLE
```

## 10. 缓存设计

新增缓存查询：

```text
get_success_parse_by_md5_format_and_option_hash(md5, file_format, option_hash)
```

规则：

- 新结果必须精确匹配 `option_hash`。
- 历史 `option_hash IS NULL` 只可匹配 `ocr_mode=off + layout_engine=docling`。
- 不同实际解析引擎不能互相命中。

输出目录建议：

```text
data/outputs/{storage_date}/{file_id}/{option_hash}/
```

原因：

- 同一文件可以保留不同解析策略结果。
- 避免 Docling 和 PP-StructureV3 结果互相覆盖。

## 11. metadata 设计

metadata 示例：

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
    "reason": "scanned_pdf_with_tables_or_seals"
  },
  "ppstructure": {
    "api_url": "http://ppstructure:8080/layout-parsing",
    "use_table_recognition": true,
    "use_seal_recognition": true,
    "page_count": 66,
    "fallback": {
      "mode": "paged_retry",
      "reason": "large_pdf",
      "page_timeout_seconds": 60,
      "preprocessed_pages": [],
      "image_fallback_pages": [27]
    }
  },
  "option_hash": "..."
}
```

Docling 路线示例：

```json
{
  "engine": "docling",
  "source_format": "pdf",
  "requested": {
    "ocr_mode": "auto",
    "layout_engine": "auto"
  },
  "actual": {
    "layout_engine": "docling",
    "ocr_applied": true,
    "reason": "scanned_pdf_simple"
  },
  "docling": {
    "ocr_backend": "rapidocr"
  },
  "option_hash": "..."
}
```

## 12. 错误码

新增错误码：

| 错误码 | 说明 |
| --- | --- |
| `invalid_ocr_mode` | OCR 模式不合法 |
| `invalid_layout_engine` | 版面解析引擎不合法 |
| `conflicting_layout_options` | 参数组合冲突 |
| `ppstructure_unavailable` | PP-StructureV3 服务不可用 |
| `ppstructure_failed` | PP-StructureV3 解析失败 |
| `ppstructure_timeout` | PP-StructureV3 调用超时 |
| `ppstructure_invalid_response` | PP-StructureV3 响应结构不合法 |

规则：

- 参数错误返回 400。
- 用户强制 `layout_engine=ppstructure` 且服务不可用时返回失败。
- `layout_engine=auto` 且 PP-StructureV3 不可用时，可以降级到 Docling 并记录 warning。

## 13. 部署设计

### 13.1 主服务镜像

两个镜像：

```text
document-to-markdown:1.2-cpu
document-to-markdown:1.2-gpu
```

差异：

- CPU/GPU 仅代表运行依赖和硬件支持不同。
- 对外 API 完全一致。
- 两个镜像都支持 Docling + RapidOCR。
- PP-StructureV3 始终作为独立服务调用。

### 13.2 模型目录

DocumentToMarkdown 主服务宿主机模型目录：

```text
/opt/document-to-markdown/models/
  docling/
  rapidocr/
```

主服务挂载：

```text
/models/docling
/models/rapidocr
```

PP-StructureV3 模型不放入 DocumentToMarkdown 项目目录，也不由主服务挂载。PP-StructureV3 独立服务按自己的部署规范挂载和管理模型，DocumentToMarkdown 只配置 `PPSTRUCTURE_API_URL` 调用服务。

### 13.3 配置

```env
OCR_DEFAULT_MODE=auto
LAYOUT_ENGINE_DEFAULT=auto
DOCLING_ARTIFACTS_PATH=/models/docling
RAPIDOCR_MODEL_PATH=/models/rapidocr
PPSTRUCTURE_API_URL=http://ppstructure:8080/layout-parsing
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

## 14. 兼容性

- 不传参数时使用 `ocr_mode=auto`、`layout_engine=auto`。
- 开放 API 仍默认不鉴权。
- 管理 API 和 `/web` 仍要求登录。
- 现有 Markdown、附件、zip 下载接口不变。
- v1.1 历史缓存按 `ocr_mode=off + layout_engine=docling` 兼容。

## 15. 风险和限制

- PP-StructureV3 服务会增加部署组件，需要单独监控和日志。
- base64 传输对大 PDF 有内存和网络开销，后续可能需要内部 URL 或共享目录优化。
- 自动判断复杂版式第一阶段可能不够准确，需要真实政府档案样本调参。
- PP-StructureV3 输出 Markdown 和图片路径需要严格归一，否则会影响现有预览和附件下载。
- OCR 和复杂版面解析耗时明显增加，必须保留超时、并发和上传大小限制。
- 第一阶段保存 PP-StructureV3 返回的 base64/data URL 图片，并允许下载与 `PPSTRUCTURE_API_URL` 同源的 URL 图片；其他来源 URL 图片不下载，只保留原始 Markdown 引用并记录 warning。
