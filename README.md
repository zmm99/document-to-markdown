# DocumentToMarkdown

DocumentToMarkdown 是一个基于 FastAPI 的文档转 Markdown 服务，适合部署在可信内网中，为业务系统提供统一的文档解析、OCR、附件导出和 Markdown 下载能力。

当前 v1.2 能力：

- 支持 PDF、DOCX、PPTX、XLSX、CSV、TXT、HTML、Markdown。
- 支持同步转换接口和异步任务接口。
- 开放 API 默认不鉴权，便于内网系统集成。
- 管理页面 `/web` 和管理类 API 需要登录。
- PDF 支持 `ocr_mode=off|auto|full`，默认 `auto`。
- 支持 `layout_engine=docling|ppstructure|auto`，默认 `auto`。
- Docling 路线内置 RapidOCR。
- PP-StructureV3 作为独立服务接入，适合扫描档案、表格、印章和复杂版式。
- 图片附件统一保存到 `assets/`，Markdown 中引用本服务附件地址。
- PP-StructureV3 返回的 base64/data URL/同源 URL 图片会本地化保存；其他来源 URL 图片保留原引用并记录 warning。

## 快速启动

```powershell
python.exe -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev,ocr-cpu]"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 9527
```

健康检查：

```powershell
curl.exe http://127.0.0.1:9527/health
```

管理页面：

```text
http://127.0.0.1:9527/web
```

## 外部系统接入

推荐外部系统优先使用异步接口：

```bash
curl -X POST "http://127.0.0.1:9527/api/tasks/convert" \
  -F "file=@scan.pdf" \
  -F "ocr_mode=auto" \
  -F "layout_engine=auto"
```

然后轮询：

```bash
curl "http://127.0.0.1:9527/api/tasks/{task_id}"
```

任务成功后使用返回的：

- `result.markdown_url` 获取 Markdown。
- `result.download_url` 下载包含 `result.md`、`metadata.json`、`assets/` 的 zip。
- `result.assets[].url` 获取图片等附件。

同步接口也可用：

```bash
curl -X POST "http://127.0.0.1:9527/api/documents/convert" \
  -F "file=@scan.pdf" \
  -F "ocr_mode=full" \
  -F "layout_engine=ppstructure"
```

详细接口文档：

- [v1.2 接口文档](docs/DocumentToMarkdown_v1.2_api.md)
- [v1.2 OpenAPI JSON](docs/DocumentToMarkdown_v1.2_openapi.json)

## OCR 和版面参数

| 参数 | 默认值 | 可选值 | 说明 |
| --- | --- | --- | --- |
| `ocr_mode` | `auto` | `off`, `auto`, `full` | OCR 策略 |
| `layout_engine` | `auto` | `auto`, `docling`, `ppstructure` | 版面解析路线 |

说明：

- `ocr_mode=off`：不 OCR，保持普通电子文档转换行为。
- `ocr_mode=auto`：默认自动判断，扫描 PDF 可走 OCR。
- `ocr_mode=full`：强制 OCR，适合整份扫描件。
- `layout_engine=docling`：强制 Docling + RapidOCR。
- `layout_engine=ppstructure`：强制 PP-StructureV3 独立服务，仅支持 PDF。
- `layout_engine=auto`：自动选择 Docling 或 PP-StructureV3。
- `ocr_mode=off&layout_engine=ppstructure` 会返回 400 参数冲突。

## 模型和 PP-StructureV3

Docling 和 RapidOCR 模型建议外置挂载：

```text
models/
  docling/
  rapidocr/
```

常用配置：

```env
DOCLING_ARTIFACTS_PATH=./models/docling
RAPIDOCR_MODEL_PATH=./models/rapidocr
PPSTRUCTURE_API_URL=http://192.168.1.4:9528/layout-parsing
```

PP-StructureV3 不嵌入主服务进程，作为独立服务部署和管理模型。

## 配置项

常用 `.env`：

```env
APP_NAME=DocumentToMarkdown
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
PPSTRUCTURE_PAGE_IMAGE_FALLBACK_ENABLED=true
ADMIN_USERNAME=admin
ADMIN_PASSWORD=admin123
SESSION_SECRET=please-change-this-secret
```

## 测试

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

真实 PP-StructureV3 服务集成测试默认跳过，需要显式设置环境变量：

```powershell
$env:RUN_PPSTRUCTURE_INTEGRATION="1"
.\.venv\Scripts\python.exe -m pytest .test\test_ppstructure_integration.py -q
```

## 安全边界

- 开放 API 默认不鉴权，只建议部署在可信内网。
- 管理页面和管理 API 使用 Cookie 登录。
- 如需公网或跨网络调用，请在网关或业务系统层增加鉴权、IP 白名单、限流和请求体大小限制。
