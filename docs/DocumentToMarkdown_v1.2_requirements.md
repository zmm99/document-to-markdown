# DocumentToMarkdown v1.2 需求文档

## 1. 版本目标

v1.2 在 v1.1 的同步转换、异步任务、文件管理、任务管理、`/web` 管理页面和 Docker 离线部署能力基础上，增加自动 OCR 和复杂扫描档案解析能力。

本版本核心目标：

- 文档转 Markdown 时默认自动判断是否需要 OCR。
- 调用方可以通过参数关闭 OCR 或强制 OCR。
- 普通文档继续优先使用 Docling 解析。
- 复杂扫描 PDF、政府档案、表格较多、印章较多的文档可以使用 PP-StructureV3 解析。
- PP-StructureV3 作为独立服务接入，同时承担版面解析和 OCR，不作为 Docling 的普通 OCR 引擎。
- RapidOCR 作为 Docling 路线的内置默认 OCR 能力，CPU 版和 GPU 版都具备。
- 所有解析结果统一输出为当前服务已有的 `result.md`、`metadata.json`、`assets/` 结构。
- Image inputs `.png`, `.jpg`, `.jpeg` are supported as single-page documents; the original image must be preserved as an asset, and OCR is supplementary text extraction only.
- 模型文件从镜像中剥离，运行时通过宿主机目录挂载。

## 2. 对外参数

v1.2 对外只暴露两个核心参数，避免调用方配置过多。

| 参数 | 类型 | 默认值 | 可选值 | 说明 |
| --- | --- | --- | --- | --- |
| `ocr_mode` | string | `auto` | `off`、`auto`、`full` | OCR 策略 |
| `layout_engine` | string | `auto` | `docling`、`ppstructure`、`auto` | 版面解析引擎 |

不再对外暴露 `ocr_engine`。内部规则如下：

- `layout_engine=docling` 时，OCR 由 Docling + RapidOCR 完成。
- PNG/JPG/JPEG image inputs are treated as one-page documents; `ocr_mode=auto/full` can use RapidOCR to extract text while preserving the original image asset.
- `layout_engine=ppstructure` 时，OCR 和版面解析都由 PP-StructureV3 服务完成。
- `layout_engine=auto` 时，由系统自动判断使用 Docling 还是 PP-StructureV3。

## 3. OCR 模式语义

### 3.1 `ocr_mode=off`

- 不执行 OCR。
- 保持 v1.1 电子文档解析行为。
- 不允许走 PP-StructureV3，因为 PP-StructureV3 本质上会执行 OCR 和版面解析。
- 如果调用方传入 `ocr_mode=off&layout_engine=ppstructure`，返回 400 参数冲突。

### 3.2 `ocr_mode=auto`

- 默认模式。
- 系统自动判断是否需要 OCR。
- 电子 PDF、有文本层的 PDF、DOCX、PPTX 等优先走 Docling。
- 扫描 PDF、整页图片 PDF、文字截图类 PDF 可走 Docling + RapidOCR。
- 扫描 PDF 且包含大量表格、印章、复杂版式时，可自动走 PP-StructureV3。

### 3.3 `ocr_mode=full`

- 强制执行 OCR。
- 适合整份扫描件。
- `layout_engine=auto` 时可优先选择 PP-StructureV3。
- `layout_engine=docling` 时使用 Docling + RapidOCR。

## 4. 解析引擎语义

### 4.1 `layout_engine=docling`

使用 Docling 作为主解析引擎。

适用场景：

- 普通 PDF。
- 有文本层的电子 PDF。
- DOCX、PPTX、XLSX、CSV、TXT、HTML 等常规格式。
- 扫描页不复杂，只需要 OCR 补充文字。

说明：

- Docling 路线默认使用 RapidOCR 作为 OCR 能力。
- RapidOCR 模型以外置模型目录形式提供。
- 后续可以服务端配置 PaddleOCR 作为 Docling OCR 后端，但 v1.2 第一阶段不开放给 API 调用方。

- PNG and JPG/JPEG inputs use the built-in image converter instead of Docling; the converter preserves the image and optionally runs RapidOCR.
### 4.2 `layout_engine=ppstructure`

使用 PP-StructureV3 独立服务作为解析后端。

适用场景：

- 政府档案扫描 PDF。
- 表格较多的扫描件。
- 印章较多的文档。
- 多栏、页眉页脚、落款、图片、表格混排的复杂扫描版式。

说明：

- PP-StructureV3 不直接嵌入 DocumentToMarkdown 主进程。
- DocumentToMarkdown 通过 HTTP API 调用 PP-StructureV3 服务。
- PP-StructureV3 输出的 Markdown、图片和结构化结果必须归一到当前服务的输出结构。

### 4.3 `layout_engine=auto`

系统自动选择解析路线。
- PNG/JPG/JPEG inputs are routed to the image converter: `ocr_mode=off` preserves only the image, while `auto/full` adds RapidOCR text.

第一阶段建议规则：

- 非 PDF 格式默认走 Docling。
- PDF 有可用文本层且不是复杂扫描件，走 Docling。
- PDF 疑似纯图片扫描件且 PP-StructureV3 服务已配置，走 PP-StructureV3。
- PDF 预检信号不足或 PP-StructureV3 服务不可用，走 Docling + RapidOCR。
- PP-StructureV3 服务不可用时，`auto` 可降级为 Docling + RapidOCR，并在 metadata 中记录 warning。

当前第一阶段的 PDF 预检只做轻量 token 判断，不引入额外 PDF 解析依赖；表格线条、印章颜色区域、扫描页复杂度判断后续增强。

## 5. API 范围

### 5.1 开放 API

继续开放且默认不鉴权：

```http
POST /api/documents/convert
POST /api/tasks/convert
GET  /api/tasks/{task_id}
GET  /api/documents/{file_id}
GET  /api/documents/{file_id}/markdown
GET  /api/documents/{file_id}/assets/{asset_name}
GET  /api/documents/{file_id}/download
GET  /api/documents/{file_id}/original
```

新增参数只影响：

```http
POST /api/documents/convert
POST /api/tasks/convert
```

### 5.2 管理 API

管理 API 和 `/web` 继续要求登录，不改变 v1.1 鉴权边界。

管理页面上传解析时需要支持：

- OCR 模式：关闭、自动、强制。
- 版面解析引擎：自动、Docling、PP-StructureV3。
- 默认值均为自动。

## 6. 输出要求

无论底层使用 Docling 还是 PP-StructureV3，对外输出必须保持一致：

```text
result.md
metadata.json
assets/
```

要求：

- Markdown 获取接口不变。
- 附件获取接口不变。
- zip 下载结构不变。
- 图片附件继续保存在 `assets/` 并在 Markdown 中引用。
- 不允许因为 OCR 或 PP-StructureV3 解析而丢弃真实图片、表格截图、印章图片等附件。

## 7. PP-StructureV3 结果归一要求

PP-StructureV3 服务返回的结果需要转换为当前服务结构。

基本处理要求：

- 遍历 `layoutParsingResults`。
- 提取每页 `markdown.text`。
- 提取每页 `markdown.images`。
- 将 `markdown.images` 中的 base64、data URL 或 PP-StructureV3 服务同源 URL 图片保存到当前文档输出目录的 `assets/`。
- 统一重命名为 `image-001.png`、`image-002.jpg` 等稳定附件名。
- 将 Markdown 中的原始图片路径替换为 `/api/documents/{file_id}/assets/{asset_name}`。
- 多页 Markdown 按页顺序合并为 `result.md`。
- 将 PP-StructureV3 的结构化结果、页数、是否启用表格识别、是否启用印章识别、实际服务信息写入 `metadata.json`。

URL 图片处理规则：

- PP-StructureV3 返回与 `PPSTRUCTURE_API_URL` 同源的 URL 图片时，主服务允许下载并保存为本地附件。
- PP-StructureV3 返回其他域名或其他端口的 URL 图片时，主服务不下载，Markdown 保持原始引用并记录 warning。
- 当前 PP-StructureV3 调用会请求 `returnMarkdownImages=true`，正常情况下应返回 base64 图片。
- URL 图片下载必须有超时、文件大小和图片 MIME 限制，避免单个图片拖垮转换任务。

## 8. PP-StructureV3 页数要求

PP-StructureV3 服务默认可能限制 PDF 或多页 TIFF 只处理前 10 页。v1.2 部署时应将该限制关闭或调大。

建议服务配置：

```yaml
Serving:
  extra:
    max_num_input_imgs: 300
```

说明：

- 业务上不希望默认只解析前 10 页。
- 当前实测环境按 300 页上限配置；如果 PP-StructureV3 服务支持且资源允许，也可配置为 `null`。
- 主服务仍必须保留上传大小限制、转换超时、任务并发限制和 PP-StructureV3 调用超时。
- 对超大扫描档案，后续可增加用户可见的分页任务、断点续跑或批处理能力。

主服务第一阶段已内置 PP-StructureV3 分页兜底：

- 当 PDF 页数达到 `PPSTRUCTURE_PAGE_RETRY_MIN_PAGES` 时，直接按页调用 PP-StructureV3，避免整份请求长时间阻塞。
- 小文档整份解析超时后，自动切换为按页重试。
- 单页解析超时后，可渲染该页并做黑白预处理后重试。
- 预处理后仍超时的页面，可退化为图片附件保留，并在 Markdown 中引用。
- metadata 中记录 `ppstructure.fallback`，包括兜底原因、总页数、单页超时、预处理页和图片保留页。

## 9. 缓存要求

v1.2 缓存不能只按 `md5 + file_format` 判断。

缓存 key 必须至少包含：

- 文件 md5。
- 文件格式。
- 请求的 `ocr_mode`。
- 请求的 `layout_engine`。
- 实际使用的 `layout_engine`。
- Docling/RapidOCR/PP-StructureV3 相关模型版本或配置指纹。

要求：

- `ocr_mode=off` 的结果不能用于 `ocr_mode=auto` 或 `ocr_mode=full`。
- Docling 结果不能误命中 PP-StructureV3 结果。
- PP-StructureV3 结果不能误命中 Docling 结果。
- 历史 v1.1 缓存可视为 `ocr_mode=off + layout_engine=docling` 的结果。

## 10. metadata 要求

metadata 中需要记录请求参数、实际选择和选择原因。

示例：

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
  "models": {
    "docling": "docling-layout-heron",
    "rapidocr": "default",
    "ppstructure": "PP-StructureV3"
  },
  "warnings": []
}
```

要求：

- `auto` 模式必须记录实际选择结果。
- 降级必须记录 warning。
- 参数冲突必须返回 400，不写入成功 metadata。

## 11. 部署要求

### 11.1 镜像版本

v1.2 后续发布两个主服务镜像：

```text
document-to-markdown:1.2-cpu
document-to-markdown:1.2-gpu
```

说明：

- CPU/GPU 差异只代表运行环境是否包含显卡相关依赖。
- 对外 API 参数不区分 CPU/GPU。
- CPU 版和 GPU 版都包含 Docling + RapidOCR 能力。
- PP-StructureV3 仍作为独立服务部署。

### 11.2 模型挂载

模型文件不放入主服务镜像，运行时挂载。

DocumentToMarkdown 主服务推荐宿主机目录：

```text
/opt/document-to-markdown/models/
  docling/
  rapidocr/
```

DocumentToMarkdown 主服务推荐容器路径：

```text
/models/docling
/models/rapidocr
```

说明：

- DocumentToMarkdown 主服务直接使用 `/models/docling` 和 `/models/rapidocr`。
- PP-StructureV3 模型不放入 DocumentToMarkdown 项目目录。
- PP-StructureV3 模型由 PP-StructureV3 独立服务自行挂载和管理。
- DocumentToMarkdown 主服务不直接读取 PP-StructureV3 模型，只配置服务地址。

## 12. 配置要求

建议新增配置：

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

说明：

- 第一阶段不提供 `OCR_ENGINE` 或 `OCR_BACKEND` 对外参数。
- 后续如需 PaddleOCR 作为 Docling OCR 后端，可增加服务端配置，不影响当前 API。

## 13. 测试要求

必须增加或更新测试：

- 不传参数时默认 `ocr_mode=auto`、`layout_engine=auto`。
- `ocr_mode=off` 保持 v1.1 兼容行为。
- `ocr_mode=off&layout_engine=ppstructure` 返回 400。
- `layout_engine=docling` 走 Docling 路线。
- `layout_engine=ppstructure` 调用 PP-StructureV3 adapter，并输出 `result.md`、`metadata.json`、`assets/`。
- PP-StructureV3 返回的 Markdown 图片能保存为附件并改写 URL。
- 不同 `ocr_mode`、`layout_engine` 不会错误命中缓存。
- 任务结果 metadata 记录 requested、actual、reason。
- 管理页面上传时能提交 OCR 模式和版面解析引擎。

## 14. 暂不纳入第一阶段

- 不把 PP-StructureV3 嵌入 DocumentToMarkdown 主进程。
- 不对外暴露 `ocr_engine`。
- 不实现 PaddleOCR 作为 Docling OCR 后端。
- 不做复杂的页级 OCR 质量评估。
- 不做任务分页解析、断点续跑和恢复。
- 不做 PP-StructureV3 服务集群管理。
