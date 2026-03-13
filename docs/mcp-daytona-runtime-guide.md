# Openwork Daytona MCP 运行架构与操作手册

本文档说明 Openwork 在 Daytona 沙箱模式下的 MCP 安装、配置与运行时链路，覆盖当前实现的真实行为与排障方法。

## 1. 目标与结论

- 推荐模式：`Snapshot 预装依赖` + `应用侧 stdio 配置` + `运行时零安装`。
- 运行态（stdio）链路是：
  `Openwork Agent -> Daytona Preview URL (https://<subdomain>.proxy.<domain>:8443/mcp) -> Sandbox 内 supergateway -> Sandbox 内 MCP stdio 进程`
- MCP 故障不会阻断 Agent 主流程：全部 MCP 不可用时，Agent 进入降级模式继续回答。

## 2. 安装与配置流程

### 2.1 在 Snapshot 预装依赖（一次性）

使用脚本：

```bash
cd server
uv run python scripts/create_daytona_snapshot.py \
  --name openwork-mcp-core-us-node22 \
  --region us \
  --verify
```

脚本当前预装项（核心）：

- Node.js 22
- `uv` / `uvx`
- `supergateway`
- `mcp-server-filesystem`
- `mcp-fetch-server@1.1.2`
- `mcp-server-starrocks`

创建成功后，将输出的 snapshot id 配到服务环境：

```bash
export DAYTONA_SNAPSHOT=<snapshot-id>
```

并重启后端服务。

### 2.2 在 Openwork 配置 MCP（应用内）

通过 MCP 管理页或 API（`/mcps`）配置 `stdio`：

- `mcp-fs`
  - `transport=stdio`
  - `command=mcp-server-filesystem`
  - `args=["/home/daytona"]`
- `web-fetch`
  - `transport=stdio`
  - `command=mcp-fetch-server`
  - `args=[]`
- `starrocks-analyst`
  - `transport=stdio`
  - `command=mcp-server-starrocks`
  - `args=[]`
  - 连接信息放在 Openwork MCP secret（`secret.env`），不要写入 snapshot 或沙箱镜像。

注意：

- Daytona 沙箱模式下不允许 `command=npx`（零安装约束）。
- 旧配置若仍是 `npx`，需要手工迁移到预装可执行命令。

## 3. 运行时工作机制（stdio）

### 3.1 实际调用路径

1. Agent 创建 runtime 时加载线程绑定的 MCP。
2. 对每个 `stdio` MCP，后端在对应沙箱内启动 `supergateway --stdio "<mcp command>"`。
3. 后端通过 Daytona SDK `create_signed_preview_url(port)` 获取 HTTPS 预览地址。
4. Agent 通过该 Preview URL 访问 `/mcp`，由 gateway 转发到沙箱内 MCP 进程。

### 3.2 与其他 transport 的区别

- `stdio`：MCP 进程运行在 Daytona 沙箱内。
- `streamable_http`/`sse`：按配置 URL 直连远端 MCP 服务，不走沙箱 gateway。

## 4. 失败开放（Fail-Open）与降级

- 若部分 MCP 失败：保留可用 MCP，Agent 继续运行。
- 若全部 MCP 失败：Agent 继续运行（无 MCP 工具），并返回一次 `mcp_degraded` 警告事件。
- 冷却策略：失败后 120 秒内跳过重连，避免每条消息重复卡顿。

说明：

- “全部 MCP 被禁用（enabled=false）”不属于“连接失败”，通常不会触发降级 warning。
- “启用但命令不可执行/不可达”属于失败，会触发降级 warning。

## 5. 验证与验收

### 5.1 服务层验证

对同一线程执行：

- `POST /mcps/{id}/test`

通过标准：

- `mcp-fs` 返回 `success=true` 且有工具列表。
- `web-fetch` 返回 `success=true` 且有工具列表。

### 5.2 Agent 端到端验证

对 `POST /agent/stream` 发送“必须使用 mcp-fs 创建文件”指令，验收：

- SSE 中无 `type=error`
- 无 `warning_type=mcp_degraded`（在 MCP 可用场景）
- 消息中出现 MCP 工具调用（如 `mcp-fs_write_file`）
- `GET /workspace/files` 和 `GET /workspace/file` 可看到目标文件与正确内容

## 6. 常见问题与定位

### 6.1 `No available runners`

- 发生阶段：新建线程或验证 sandbox 创建。
- 结论：Daytona 区域容量问题，不是 MCP 配置问题。
- 处理：切换可用 region 或等待 runner 资源恢复。

### 6.2 `set: Illegal option -o pipefail`

- 发生阶段：沙箱内 `sh` 执行启动脚本。
- 处理：脚本使用 `set -eu`，避免 `pipefail`（`sh` 不兼容）。

### 6.3 `ERR_REQUIRE_ESM` / Node 版本不兼容

- 根因：Node 与 MCP 包/依赖版本组合不兼容。
- 建议：新 snapshot 使用 Node 22 基线，fetch MCP 使用当前文档中的固定版本。

### 6.4 Preview URL 握手超时

- 现象：`https://<subdomain>.proxy.<domain>:8443/mcp` 超时或 TLS 握手失败。
- 重点排查：
  - `proxy.<domain>:8443` TLS 与路由是否健康
  - 子域是否正确映射到 runner/sandbox 端口
  - 网络与代理策略是否阻断该域名/端口

## 7. 推荐版本基线

- Snapshot Node：`22.x`
- `mcp-fetch-server`：`1.1.2`
- `mcp-server-filesystem`：随 snapshot 预装同步
- `supergateway`：随 snapshot 预装同步

如需升级，先在临时 sandbox 里做 `--help` 与 `/mcps/{id}/test` 双重验证，再推广到正式 snapshot。
