# Daytona 本机私有化部署（Openwork）

本方案把 Daytona 控制面和 Runner 跑在你本机，不使用 Daytona 云。

## 适用场景

- 你希望 Openwork 的 sandbox 执行全部落在本地基础设施。
- 你接受官方 OSS docker-compose 形态更偏开发/内网验证，不作为生产级 HA 方案。

## 前置条件

- Docker + Docker Compose 可用
- Openw
- 后端使用 `server/.venv` 环境运行

## 1) 启动本地 Daytona

在仓库根目录执行：

```bash
server/scripts/daytona_local_up.sh
```

说明：

- 该脚本会从 `daytonaio/daytona` 拉取官方 `docker/` 部署文件到 `.run/daytona-local/`。
- 默认使用 `main` 分支，可通过环境变量指定版本：

```bash
DAYTONA_GIT_REF=v0.149.0 server/scripts/daytona_local_up.sh
```

- 如果你只想先准备文件而不启动容器：

```bash
server/scripts/daytona_local_up.sh --prepare-only
```

## 2) 生成本地 API Key

- 打开 Dashboard：`http://localhost:3000/dashboard`
- 默认本地登录账号：
  - email: `dev@daytona.io`
  - password: `password`
- 在 Dashboard 中创建 API Key。

## 3) 配置 Openwork 后端连接本地 Daytona

复制模板：

```bash
cp server/.env.daytona.local.example server/.env
```

然后把 `DAYTONA_API_KEY` 改成你刚创建的 key。

如果后端跑在 devcontainer，请把：

```bash
DAYTONA_API_URL=http://host.docker.internal:3000/api
```

## 4) 启动 Openwork 后端

```bash
cd server
.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## 5) 验证

- 在前端点击 `New Thread`。
- Daytona 本地 Dashboard 中应出现对应 sandbox。
- Openwork Files 面板可看到 sandbox 工作区。

## 停止 Daytona 本地栈

```bash
server/scripts/daytona_local_down.sh
```

如需连同 volume 一并清理：

```bash
server/scripts/daytona_local_down.sh --volumes
```
