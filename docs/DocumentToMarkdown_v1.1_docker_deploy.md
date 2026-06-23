# DocumentToMarkdown v1.1 Docker 部署说明

本文档用于在 Ubuntu 内网服务器上部署 DocumentToMarkdown v1.1。当前推荐镜像方案为：

- CPU-only PyTorch，不依赖显卡。
- 多阶段构建，最终镜像不包含编译工具链。
- 内置本地 `models/docling` 模型目录，服务器无需联网下载 Docling 模型。
- 数据统一挂载到 `/data`，便于持久化和备份。

## 镜像信息

当前推荐镜像标签：

```text
document-to-markdown:1.1
```

本地导出的镜像包：

```text
release-docker/document-to-markdown-1.1.tar
```

镜像已使用 CPU-only 依赖构建，`torch` 和 `torchvision` 版本为：

```text
torch==2.12.0+cpu
torchvision==0.27.0+cpu
```

## 本地构建

如果需要重新构建镜像，推荐使用本地模型版 Dockerfile：

```bash
docker build \
  -f Dockerfile.local-models \
  -t document-to-markdown:1.1 \
  --build-arg DEBIAN_MIRROR=https://mirrors.tuna.tsinghua.edu.cn/debian \
  --build-arg PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple \
  .
```

该构建会从 `models/docling` 复制模型到镜像中，不会执行在线模型下载。

如果需要自定义 PyTorch CPU 源或版本：

```bash
docker build \
  -f Dockerfile.local-models \
  -t document-to-markdown:1.1 \
  --build-arg PYTORCH_CPU_INDEX_URL=https://download.pytorch.org/whl/cpu \
  --build-arg TORCH_VERSION=2.12.0+cpu \
  --build-arg TORCHVISION_VERSION=0.27.0+cpu \
  .
```

## 导出镜像

```bash
mkdir -p release-docker
docker save -o release-docker/document-to-markdown-1.1.tar document-to-markdown:1.1
```

## Ubuntu 服务器导入

将 `document-to-markdown-1.1.tar` 拷贝到 Ubuntu 服务器后执行：

```bash
docker load -i document-to-markdown-1.1.tar
```

确认镜像已导入：

```bash
docker images document-to-markdown
```

## 启动服务

推荐将数据目录挂载到宿主机：

```bash
mkdir -p /opt/document-to-markdown/data

docker run -d \
  --name document-to-markdown \
  --restart unless-stopped \
  -p 9527:9527 \
  -e DATA_DIR=/data \
  -e API_PREFIX=/api \
  -e ADMIN_USERNAME=admin \
  -e ADMIN_PASSWORD='change-this-password' \
  -e SESSION_SECRET='change-this-random-secret' \
  -v /opt/document-to-markdown/data:/data \
  document-to-markdown:1.1
```

## 访问地址

```text
健康检查：http://服务器IP:9527/health
管理页面：http://服务器IP:9527/web
接口文档：http://服务器IP:9527/docs
开放接口：http://服务器IP:9527/api
```

## 常用命令

查看日志：

```bash
docker logs -f document-to-markdown
```

停止服务：

```bash
docker stop document-to-markdown
```

删除容器：

```bash
docker rm document-to-markdown
```

重新启动：

```bash
docker start document-to-markdown
```

更新镜像时建议流程：

```bash
docker stop document-to-markdown
docker rm document-to-markdown
docker load -i document-to-markdown-1.1.tar
docker run -d \
  --name document-to-markdown \
  --restart unless-stopped \
  -p 9527:9527 \
  -e DATA_DIR=/data \
  -e API_PREFIX=/api \
  -e ADMIN_USERNAME=admin \
  -e ADMIN_PASSWORD='change-this-password' \
  -e SESSION_SECRET='change-this-random-secret' \
  -v /opt/document-to-markdown/data:/data \
  document-to-markdown:1.1
```

## Docker Compose

仓库内的 `docker-compose.yml` 已指向 `Dockerfile.local-models`：

```bash
docker compose build
docker compose up -d
```

如果使用 `.env`，建议至少配置：

```env
ADMIN_USERNAME=admin
ADMIN_PASSWORD=change-this-password
SESSION_SECRET=change-this-random-secret
DATA_DIR=/data
API_PREFIX=/api
MAX_UPLOAD_SIZE_MB=100
CONVERT_TIMEOUT_SECONDS=300
MAX_CONCURRENT_CONVERSIONS=2
TASK_WORKER_COUNT=1
```

## 资源建议

无显卡服务器可以正常运行。建议配置：

```text
最低：4 核 CPU / 8GB 内存
推荐：8 核 CPU / 16GB 内存
```

复杂 PDF、图片较多的文档或大文件转换会明显消耗 CPU 和内存，建议生产环境限制上传大小、并发转换数量和转换超时时间。
