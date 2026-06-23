# DocumentToMarkdown v1.2 开发计划

## 1. 目标范围

本计划基于 `DocumentToMarkdown_v1.2_requirements.md` 和 `DocumentToMarkdown_v1.2_design.md`。

v1.2 第一阶段目标：

- API 支持 `ocr_mode=off|auto|full`，默认 `auto`。
- API 支持 `layout_engine=docling|ppstructure|auto`，默认 `auto`。
- 不对外暴露 `ocr_engine`。
- Docling 路线接入 RapidOCR 作为内置 OCR。
- PP-StructureV3 作为独立服务接入，并归一输出为当前结果结构。
- 模型文件改为外置挂载。
- 管理页面上传解析支持 OCR 模式和版面解析引擎。
- 缓存按解析参数和实际引擎隔离。
- 补充测试、接口文档、OpenAPI 和 Docker 部署文档。

## 2. 开发原则

- 先实现参数和缓存隔离，再接入 OCR 和 PP-StructureV3。
- 每阶段可测试、可回退。
- 保持开放 API 不鉴权，管理 API 和 `/web` 继续登录保护。
- 不引入对外复杂配置。
- 不把 PP-StructureV3 嵌入主服务进程。
- 不破坏现有 Markdown、附件、zip 下载结构。

## 3. 阶段一：依赖和基线确认

### 开发内容

- 运行现有测试，确认 v1.1 基线。
- 确认当前 Docling 版本和 RapidOCR extra 安装方式。
- 确认 PP-StructureV3 服务部署方式和 `/layout-parsing` 返回结构。
- 确认 PP-StructureV3 服务如何关闭默认 10 页限制。
- 准备最小扫描 PDF、带表格扫描 PDF、带印章扫描 PDF 样例。

### 验收标准

- 现有测试通过，或记录当前失败原因。
- 明确 RapidOCR 模型目录挂载方式。
- 明确 PP-StructureV3 服务调用方式。
- 明确 PP-StructureV3 服务配置 `max_num_input_imgs: 300` 或 `null` 是否生效。

## 4. 阶段二：参数模型与配置

### 开发内容

- 新增 `app/core/conversion_options.py`。
- 解析并校验：
  - `ocr_mode`
  - `layout_engine`
- 新增配置：
  - `OCR_DEFAULT_MODE=auto`
  - `LAYOUT_ENGINE_DEFAULT=auto`
  - `RAPIDOCR_MODEL_PATH=/models/rapidocr`
  - `PPSTRUCTURE_API_URL`
  - `PPSTRUCTURE_TIMEOUT_SECONDS`
  - `PPSTRUCTURE_USE_TABLE_RECOGNITION`
  - `PPSTRUCTURE_USE_SEAL_RECOGNITION`
- 生成稳定 `option_hash`。
- 更新 `.env.example`。

### 验收标准

- 不传参数时默认 `auto/auto`。
- 非法参数返回 400。
- `ocr_mode=off&layout_engine=ppstructure` 返回 400。
- 相同参数生成相同 `option_hash`。

## 5. 阶段三：数据库迁移和缓存隔离

### 开发内容

- `parse_records` 增加：
  - `option_hash`
  - `options_json`
- `conversion_tasks` 增加：
  - `option_hash`
  - `options_json`
- 增加 schema migration。
- 新增按 `md5 + file_format + option_hash` 查询成功缓存。
- 输出目录增加 `option_hash` 层级。
- 历史 v1.1 缓存按 `ocr_mode=off + layout_engine=docling` 兼容。

### 验收标准

- 旧数据库启动后自动补齐字段。
- Docling 和 PP-StructureV3 结果不会互相命中缓存。
- `ocr_mode=off` 不会命中 `auto/full` 结果。
- 同一文件不同参数结果不会互相覆盖。

## 6. 阶段四：转换链路传参

### 开发内容

- `run_converter_with_timeout()` 支持传入 `ConversionOptions`。
- `conversion_worker` 支持接收并反序列化 options。
- `Converter` 协议支持 options。
- 同步转换接口传 options。
- 异步任务保存 options，worker 从任务记录读取 options。
- 重试任务继承原任务 options。

### 验收标准

- 不传参数时现有格式仍可转换。
- 同步转换和异步任务都能携带 options。
- 重试任务参数不丢失。
- 转换超时和并发限制仍生效。

## 7. 阶段五：自动路由

### 开发内容

- 新增 `app/core/layout_router.py`。
- 对 PDF 做轻量预检：
  - 是否有文本层。
  - 是否主要为整页图片。
  - 是否疑似复杂扫描版式。
- 生成 `LayoutDecision`：
  - `actual_layout_engine`
  - `ocr_applied`
  - `reason`
  - `warnings`
- `layout_engine=auto` 根据决策选择 Docling 或 PP-StructureV3。
- 第一阶段自动路由只做轻量 PDF token 预检：电子 PDF 走 Docling，疑似纯图片扫描件且 PP-StructureV3 已配置时走 PP-StructureV3，其余保守走 Docling。

### 验收标准

- 非 PDF 默认走 Docling。
- `layout_engine=docling` 强制走 Docling。
- `layout_engine=ppstructure` 强制走 PP-StructureV3。
- `layout_engine=auto` 能记录实际选择原因。
- `layout_engine=auto` 对疑似纯图片扫描 PDF 能自动选择 PP-StructureV3。
- PP-StructureV3 不可用时，auto 能按规则降级或失败。

## 8. 阶段六：Docling + RapidOCR 接入

### 开发内容

- 修改 `DoclingConverter`，按 `ocr_mode` 配置 PDF pipeline。
- `off`：`do_ocr=False`。
- `auto`：`do_ocr=True`，非整页强制 OCR。
- `full`：`do_ocr=True`，强制整页 OCR。
- 接入 RapidOCR 模型路径。
- metadata 记录 Docling 路线、RapidOCR、requested、actual、reason。
- 保留现有图片附件导出逻辑。

### 验收标准

- `ocr_mode=off` 与 v1.1 行为兼容。
- `ocr_mode=auto/full` 能启用 OCR。
- 开启 OCR 后图片附件仍保留。
- metadata 记录 `docling.ocr_backend=rapidocr`。

## 9. 阶段七：PP-StructureV3 服务接入

### 开发内容

- 新增 PP-StructureV3 HTTP client。
- 新增 PP-StructureV3 response adapter。
- 调用 `/layout-parsing`。
- 第一阶段使用 base64 传输文件。
- 支持表格识别和印章识别配置。
- 处理服务错误、超时、响应结构异常。
- 对大页数 PDF 支持按页调用 PP-StructureV3。
- 对整份解析超时支持自动切换按页重试。
- 对慢页支持渲染预处理后重试。
- 对仍然超时的页面支持图片附件保留。

### 验收标准

- 强制 `layout_engine=ppstructure` 能调用服务。
- 服务不可用时返回明确错误。
- 超时返回明确错误。
- PP-StructureV3 返回结果能转换为 `ConvertResult`。
- 大页数 PDF 不因单页超时导致整份失败。
- 图片保留页在 metadata 中可追踪。

## 10. 阶段八：PP-StructureV3 输出归一

### 开发内容

- 遍历 `layoutParsingResults`。
- 合并每页 `markdown.text`。
- 解析 `markdown.images`。
- 将 base64 图片保存到 `assets/`。
- 统一附件命名。
- 替换 Markdown 图片路径为当前附件 URL。
- 将 `prunedResult`、页数、服务配置写入 metadata。
- 将分页兜底、预处理页、图片保留页写入 metadata。

### 验收标准

- 生成 `result.md`。
- 生成 `metadata.json`。
- 生成 `assets/`。
- Markdown 中图片能通过当前附件接口访问。
- zip 下载包含 PP-StructureV3 生成的附件。

## 11. 阶段九：API 和管理页面

### 开发内容

- `POST /api/documents/convert` 增加：
  - `ocr_mode`
  - `layout_engine`
- `POST /api/tasks/convert` 增加同样参数。
- 管理页面上传区域增加：
  - OCR 模式选择。
  - 版面解析引擎选择。
- 默认均为自动。
- 文件详情继续展示 metadata。

### 验收标准

- 开放 API 不登录仍可调用。
- 管理页面可提交两个参数。
- 参数错误页面有明确提示。
- 任务完成后可预览 Markdown 和附件。

## 12. 阶段十：文档和 OpenAPI

### 开发内容

- 更新 v1.2 接口文档。
- 更新 v1.2 OpenAPI。
- 更新 Docker 部署文档：
  - CPU/GPU 镜像差异。
  - 模型外置挂载。
  - PP-StructureV3 独立服务部署。
  - `max_num_input_imgs: 300` 或 `null` 配置。
- 更新 README。
- 更新 `.env.example`。

### 验收标准

- 文档不再出现对外 `ocr_engine` 参数。
- 文档明确 `ocr_mode` 和 `layout_engine` 默认值。
- 文档明确 PP-StructureV3 输出归一规则。
- Docker 文档可指导离线部署。

## 13. 阶段十一：测试

### 自动化测试

- 参数解析测试。
- 参数冲突测试。
- 缓存隔离测试。
- 同步转换 options 传递测试。
- 异步任务 options 保存和 worker 读取测试。
- 重试任务继承 options 测试。
- Docling 路线 metadata 测试。
- PP-StructureV3 adapter 单元测试。
- PP-StructureV3 图片保存和 Markdown 路径替换测试。
- 管理 API 鉴权回归测试。

### 手工测试

- 普通电子 PDF：默认 auto。
- 扫描 PDF：默认 auto。
- 扫描 PDF：强制 Docling。
- 扫描 PDF：强制 PP-StructureV3。
- 带表格扫描 PDF。
- 带印章扫描 PDF。
- 管理页面上传、轮询、预览、下载 zip。
- Docker CPU 镜像启动。
- PP-StructureV3 服务启动和调用。

### 验收标准

- 自动化测试通过。
- v1.1 关键回归通过。
- PP-StructureV3 结果能稳定归一。
- 附件保留逻辑通过。
- 缓存无错误命中。

## 14. 阶段十二：发布准备

### 开发内容

- 构建 CPU 镜像。
- 如环境具备，构建 GPU 镜像。
- 准备模型目录挂载说明。
- 准备 PP-StructureV3 服务部署说明。
- 运行 smoke test。
- 做代码审查。

### 验收标准

- 主服务镜像不内置模型。
- 挂载模型后 Docling + RapidOCR 可用。
- PP-StructureV3 服务可独立启动。
- 主服务可调用 PP-StructureV3。
- release 文档和实际行为一致。

## 15. 推荐实现顺序

1. 参数模型和配置。
2. 数据库迁移和缓存隔离。
3. 转换链路传参。
4. 自动路由。
5. Docling + RapidOCR。
6. PP-StructureV3 client。
7. PP-StructureV3 adapter 和输出归一。
8. API 参数接入。
9. 管理页面。
10. 测试。
11. 文档和 Docker 部署说明。

## 16. 第一阶段完成标准

- 默认 `ocr_mode=auto`、`layout_engine=auto`。
- `ocr_mode=off|auto|full` 可用。
- `layout_engine=docling|ppstructure|auto` 可用。
- 不对外暴露 `ocr_engine`。
- Docling 路线使用 RapidOCR。
- PP-StructureV3 作为独立服务可用。
- PP-StructureV3 输出归一为当前结构。
- 图片附件保留。
- 缓存隔离正确。
- 管理页面可配置两个参数。
- 文档和 OpenAPI 更新完成。

## 17. 当前发布前检查项

当前代码阶段已经完成核心 OCR/PP-StructureV3 功能和真实样本验证；正式发布前仍建议保留以下检查：

- 校对 v1.2 文档、README、接口文档和 OpenAPI 是否与最终 API 一致。
- Docker CPU 镜像构建和启动验证。
- GPU 镜像方案确认，至少明确依赖差异和运行参数。
- 模型目录外置挂载验证，确认镜像不再依赖内置模型。
- PP-StructureV3 服务部署文档补充，包括页数上限、服务地址、模型挂载和资源限制。
- 用真实政府档案样本再跑一轮 smoke test，记录耗时、页数、附件数量和 fallback 页。
