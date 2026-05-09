# DocumentToMarkdown v1.1 开发计划

## 1. 目标范围

本计划基于 `DocumentToMarkdown_v1.1_requirements.md` 和 `DocumentToMarkdown_v1.1_design.md`，用于指导 v1.1 的开发、测试和发布。

v1.1 的核心目标：

- 增加异步转换任务接口，支持上传、查询状态、查询进度、获取结果。
- 增加文件列表和任务列表接口，便于管理已转换文件和历史任务。
- 增加 `/web` 管理页面，支持登录、上传解析、文件查询、任务管理、Markdown 预览、缓存删除和文件删除。
- 保留 v1.0 同步转换接口，保证已有系统继续可用。
- 开放 API 暂不鉴权，满足其他系统直接接入；管理页面和管理类 API 需要登录。

## 2. 开发原则

- 兼容优先：不破坏 v1.0 已有接口、返回结构和文件获取方式。
- 开放 API 与管理 API 分层：上传解析、状态查询、文档/附件获取保持开放；删除、重试、取消、列表管理等操作要求登录。
- 简单可控：v1.1 使用进程内任务队列，不引入 Redis、Celery、复杂权限系统或 API Token。
- 进度可读：任务状态必须返回 `progress`、`stage`、`message`，便于外部系统轮询。
- 本地内网定位：开放 API 无鉴权，仅适合本机或可信内网部署，文档中继续明确该边界。
- 每阶段可验收：每个阶段完成后必须能运行对应测试或手工验证，不把风险积压到最后。

## 3. 阶段一：基线确认与兼容检查

### 开发内容

- 确认当前 v1.0 代码、测试、文档状态。
- 运行现有测试，确保进入 v1.1 前没有已知回归。
- 确认以下 v1.0 开放接口继续可用：
  - `POST /api/documents/convert`
  - `GET /api/documents/{file_id}`
  - `GET /api/documents/{file_id}/markdown`
  - `GET /api/documents/{file_id}/assets/{asset_name}`
  - `GET /api/documents/{file_id}/download`

### 验收标准

- 现有测试通过。
- PDF、DOCX、TXT、MD、CSV、HTML、XLSX、PPTX 等格式转换能力保持正常。
- v1.0 同步转换接口返回结构不发生破坏性变化。

## 4. 阶段二：配置与登录能力

### 开发内容

- 在配置中新增管理登录相关环境变量：
  - `ADMIN_USERNAME`
  - `ADMIN_PASSWORD`
  - `SESSION_SECRET`
  - `SESSION_EXPIRE_HOURS`
- 新增认证模块：
  - `app/core/auth.py`
  - `app/api/auth.py`
- 提供登录接口：
  - `POST /api/auth/login`
  - `POST /api/auth/logout`
  - `GET /api/auth/me`
- 登录成功后写入 HttpOnly Cookie。
- 新增管理接口依赖，用于保护管理类 API 和 `/web` 页面。

### 验收标准

- 正确账号密码可以登录。
- 错误账号密码返回 401。
- 未登录访问管理 API 返回 401。
- 已登录访问管理 API 正常。
- 开放 API 不受登录影响。

## 5. 阶段三：任务数据模型与仓储

### 开发内容

- 新增 `conversion_tasks` 表，用于记录异步转换任务。
- 建议字段：
  - `task_id`
  - `file_id`
  - `original_filename`
  - `status`
  - `progress`
  - `stage`
  - `message`
  - `error_code`
  - `error_message`
  - `cached`
  - `created_at`
  - `started_at`
  - `finished_at`
  - `updated_at`
- 新增任务仓储模块：
  - `app/db/task_repository.py`
- 支持任务创建、状态更新、进度更新、详情查询、分页列表、取消标记、删除记录。
- 服务启动时处理未完成任务：
  - `queued` 可标记为 `cancelled` 或 `failed`
  - `running` 标记为 `failed`
  - 错误信息说明服务重启导致任务中断

### 验收标准

- 可以创建任务记录。
- 可以按 `task_id` 查询任务。
- 可以按状态、文件名、时间分页查询任务。
- 任务状态和进度更新能正确持久化。
- 服务重启后的遗留任务不会一直停留在 `running`。

## 6. 阶段四：进程内异步任务队列

### 开发内容

- 新增任务队列模块：
  - `app/core/task_queue.py`
- 使用应用生命周期启动后台 worker。
- 使用现有转换隔离能力执行实际转换。
- 支持任务状态流转：
  - `queued`
  - `running`
  - `success`
  - `failed`
  - `timeout`
  - `cancelled`
- 支持进度阶段：
  - `0`：任务已创建
  - `10`：等待执行
  - `20`：文件校验完成
  - `40`：开始转换
  - `80`：写入结果
  - `90`：记录元数据
  - `100`：完成
- 支持取消排队中的任务。
- 对运行中的任务，v1.1 可采用尽力取消策略，返回明确状态说明。

### 验收标准

- 异步任务可以从 `queued` 自动进入 `running`。
- 转换成功后进入 `success`，并能获取 `file_id` 和结果地址。
- 转换失败后进入 `failed` 或 `timeout`，错误信息可诊断。
- 排队任务可以取消。
- 并发任务数量受配置控制。

## 7. 阶段五：异步任务 API

### 开发内容

开放 API：

- `POST /api/tasks/convert`
  - 上传文件并创建异步转换任务。
  - 返回 `task_id`、`status`、`progress`、`status_url`。
- `GET /api/tasks/{task_id}`
  - 查询任务状态、进度、错误信息和结果地址。

管理 API：

- `GET /api/tasks`
  - 分页查询任务列表。
- `POST /api/tasks/{task_id}/retry`
  - 对失败任务发起重试，建议创建新任务并关联原任务。
- `POST /api/tasks/{task_id}/cancel`
  - 取消排队任务，运行中任务按尽力取消处理。
- `DELETE /api/tasks/{task_id}`
  - 删除任务记录，不删除文档文件。

### 验收标准

- 外部系统无需登录即可上传异步任务。
- 外部系统无需登录即可查询单个任务状态。
- 任务成功后响应中包含文档详情、Markdown、下载、附件访问地址。
- 管理类任务列表、重试、取消、删除接口必须登录。
- 缓存命中时可以快速返回成功任务，并标记 `cached=true`。

## 8. 阶段六：文件管理 API

### 开发内容

开放 API：

- 保留 `GET /api/documents/{file_id}`。
- 保留 `GET /api/documents/{file_id}/markdown`。
- 保留 `GET /api/documents/{file_id}/assets/{asset_name}`。
- 保留 `GET /api/documents/{file_id}/download`。

管理 API：

- `GET /api/documents`
  - 分页查询文档列表。
  - 支持文件名、格式、时间、是否有附件等条件。
- `POST /api/documents/{file_id}/reconvert`
  - 强制重新转换。
- `DELETE /api/documents/{file_id}/cache`
  - 删除转换结果缓存。
- `DELETE /api/documents/{file_id}`
  - 删除文档记录、上传文件、转换结果和附件。

### 验收标准

- 其他系统仍能通过开放 API 获取文档、Markdown、附件和下载文件。
- 管理页面能查询文件列表和文件详情。
- 删除缓存后，再次转换能重新生成结果。
- 删除文件后，文档详情、Markdown、附件和下载接口均返回合理错误。

## 9. 阶段七：管理页面 `/web`

### 开发内容

- 新增 Web 路由：
  - `app/api/web.py`
- 新增静态资源目录：
  - `app/web/static/index.html`
  - `app/web/static/app.js`
  - `app/web/static/style.css`
- 页面功能：
  - 登录/退出。
  - 上传文件并创建异步任务。
  - 查看任务列表、状态、进度、错误信息。
  - 取消、重试、删除任务记录。
  - 查看文件列表。
  - 查看文件详情和附件列表。
  - Markdown 预览。
  - 下载 Markdown。
  - 删除缓存。
  - 删除文件。
- 页面风格：
  - 简洁后台管理界面。
  - 不依赖外部 CDN。
  - 首屏直接是管理工作台，不做营销页。

### 验收标准

- 未登录访问 `/web` 时进入登录状态。
- 登录后可以完成上传、任务轮询、Markdown 预览、文件查询和删除操作。
- 任务进度在页面中可见。
- 接口错误在页面中有明确提示。
- 页面在常见桌面分辨率下无明显布局错乱。

## 10. 阶段八：文档与 OpenAPI 更新

### 开发内容

- 更新接口文档。
- 更新 OpenAPI 文档。
- 更新 README：
  - v1.1 新能力说明。
  - 启动方式。
  - `/web` 管理地址。
  - `.env` 管理账号配置。
  - 开放 API 与管理 API 的鉴权边界。
- 更新 `.env.example`。

### 验收标准

- 文档覆盖同步转换、异步转换、任务查询、文件获取、管理接口和登录。
- OpenAPI 与实际接口保持一致。
- README 能指导用户完成启动、登录和基本转换测试。

## 11. 阶段九：测试与代码审查

### 测试范围

- 单元测试：
  - 认证逻辑。
  - 任务仓储。
  - 任务状态流转。
  - 文件列表和任务列表查询。
- 接口测试：
  - 同步转换。
  - 异步转换。
  - 任务查询。
  - 管理接口鉴权。
  - 删除缓存。
  - 删除文件。
- 手工测试：
  - `/web` 登录。
  - 上传文件。
  - 查看任务进度。
  - 预览 Markdown。
  - 下载 Markdown。
  - 删除缓存和文件。
- 回归测试：
  - PDF 图片附件可访问。
  - DOCX fallback 可用。
  - 表格时间格式仍为北京时间 `yyyy-MM-dd HH:mm:ss`。
  - 大文件上传限制仍生效。

### 验收标准

- 自动化测试通过。
- 常用格式转换通过。
- v1.0 同步接口兼容。
- 开放 API 无需登录。
- 管理 API 和 `/web` 需要登录。
- 无明显资源泄露、路径穿越或裸 500 问题。

## 12. 阶段十：发布准备

### 开发内容

- 运行完整测试。
- 生成或更新 release 包。
- 检查 release 中是否包含：
  - 应用代码。
  - `run.bat`
  - `.env.example`
  - docs 文档。
  - OpenAPI 文档。
  - 发布说明。
- 做 release 目录 smoke test。

### 验收标准

- release 包可启动。
- `http://127.0.0.1:9527/docs` 可访问。
- `http://127.0.0.1:9527/web` 可访问。
- 同步转换接口可用。
- 异步转换接口可用。
- 管理页面可登录并完成基本操作。

## 13. 推荐实现顺序

1. 配置与登录能力。
2. 任务表和任务仓储。
3. 进程内任务队列。
4. 异步任务开放 API。
5. 任务管理 API。
6. 文件列表与文件管理 API。
7. `/web` 管理页面。
8. 文档、OpenAPI、README 更新。
9. 全量测试与发布。

## 14. v1.1 完成标准

- 保留并兼容 v1.0 同步转换能力。
- 其他系统可以通过开放 API 完成上传、查询状态、获取 Markdown、获取附件和下载结果。
- 管理员可以通过 `/web` 登录并管理任务和文件。
- 任务状态包含可轮询的进度信息。
- 管理类 API 已登录保护。
- 删除缓存和删除文件两个能力都可用。
- 文档、OpenAPI、README、`.env.example` 与实际功能一致。
- 自动化测试和核心格式手工测试通过。

## 15. 暂不纳入 v1.1 的内容

- API Token 或多租户权限体系。
- Redis、Celery、外部消息队列。
- OCR 识别增强。
- 旧版 Office 格式 `.doc`、`.xls`、`.ppt`。
- WebSocket 或 SSE 实时进度推送。
- 复杂用户体系和角色权限。

