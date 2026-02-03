# OpenWork BS 架构系统说明书

> 本文档说明 OpenWork 的 Browser-Server (BS) 架构，涵盖后端 FastAPI 服务和前端 React 应用的设计、API 接口、模块组织及开发指南。

---

## 1. 架构概览

### 1.1 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                        Browser (前端)                        │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  React 19 + TypeScript + Vite 7                    │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐           │   │
│  │  │ 聊天界面  │ │ 文件查看  │ │ 看板视图  │           │   │
│  │  └──────────┘ └──────────┘ └──────────┘           │   │
│  │  ┌─────────────────────────────────────────────┐   │   │
│  │  │      ThreadContext (线程状态管理)             │   │   │
│  │  │      Zustand Store (全局状态)                │   │   │
│  │  └─────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────┘   │
└──────────────────────────────┬──────────────────────────────┘
                               │ HTTP/SSE
                               │ REST API + Server-Sent Events
┌──────────────────────────────┴──────────────────────────────┐
│                        Server (后端)                         │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  FastAPI + SQLAlchemy + MySQL                       │   │
│  │  ┌─────────────────────────────────────────────┐   │   │
│  │  │  API 路由层                                   │   │   │
│  │  │  /auth  /threads  /models  /workspace        │   │   │
│  │  │  /agent (SSE 流式响应)                        │   │   │
│  │  └─────────────────────────────────────────────┘   │   │
│  │  ┌─────────────────────────────────────────────┐   │   │
│  │  │  DeepAgent Runtime (LangGraph)               │   │   │
│  │  │  - LangChain 工具调用                         │   │   │
│  │  │  - MySQL Checkpoint 持久化                   │   │   │
│  │  │  - 人机交互 (HITL) 中断支持                   │   │   │
│  │  └─────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  数据层                                             │   │
│  │  - MySQL: users, threads, runs, checkpoints        │   │
│  │  - 文件系统: 用户工作空间                          │   │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 技术栈

| 层级 | 技术 | 版本 |
|------|------|------|
| **后端框架** | FastAPI | 0.110+ |
| **数据库** | MySQL + SQLAlchemy ORM | 2.0+ |
| **迁移工具** | Alembic | 1.13+ |
| **AI 框架** | LangChain + LangGraph | 0.2+ |
| **Deep Agents** | deepagents | 0.3.9+ |
| **前端框架** | React | 19.2.1 |
| **构建工具** | Vite | 7.2.6 |
| **状态管理** | Zustand | 5.0.3 |
| **UI 组件** | Radix UI + Tailwind CSS 4.0 | - |
| **类型系统** | TypeScript | 5.9.3 |

### 1.3 目录结构

```
langchain-openwork/
├── server/                      # FastAPI 后端
│   ├── app/
│   │   ├── api/                 # API 路由模块
│   │   │   ├── auth.py          # 认证接口
│   │   │   ├── threads.py       # 线程管理
│   │   │   ├── models.py        # 模型配置
│   │   │   ├── workspace.py     # 文件系统操作
│   │   │   ├── agent.py         # AI 智能体流式接口
│   │   │   └── admin.py         # 管理功能
│   │   ├── main.py              # FastAPI 应用入口
│   │   ├── config.py            # 配置加载
│   │   ├── db.py                # 数据库连接
│   │   ├── models.py            # SQLAlchemy 数据模型
│   │   ├── schemas.py           # Pydantic 数据模式
│   │   ├── auth.py              # JWT 认证逻辑
│   │   ├── crypto.py            # 加密/解密工具
│   │   ├── deps.py              # 依赖注入
│   │   ├── model_catalog.py     # 模型目录
│   │   ├── system_prompt.py     # 系统提示词
│   │   ├── agent_tools.py       # Agent 工具定义
│   │   ├── deep_agent_runtime.py # Deep Agent 运行时
│   │   └── checkpointer_mysql.py # LangGraph MySQL 检查点
│   ├── alembic/                 # 数据库迁移
│   ├── config.yaml              # 配置文件
│   └── pyproject.toml           # Python 依赖
│
└── web/                         # React 前端
    ├── src/
    │   ├── components/
    │   │   ├── chat/            # 聊天相关组件
    │   │   ├── sidebar/         # 侧边栏组件
    │   │   ├── panels/          # 右侧面板组件
    │   │   ├── tabs/            # 标签页组件
    │   │   ├── kanban/          # 看板视图组件
    │   │   └── ui/              # 基础 UI 组件
    │   ├── lib/
    │   │   ├── store.ts         # Zustand 全局状态
    │   │   ├── thread-context.tsx # 线程上下文
    │   │   ├── window-api.ts    # Window API 注入
    │   │   └── types.ts         # 类型定义
    │   ├── App.tsx              # 应用入口
    │   └── main.tsx             # React 挂载点
    ├── index.html
    ├── vite.config.ts           # Vite 配置
    └── package.json             # NPM 依赖
```

---

## 2. 后端架构 (Server)

### 2.1 应用启动

入口文件: `server/app/main.py`

```python
app = FastAPI(title="Openwork Server")

# 路由注册
app.include_router(auth_router.router)      # /auth
app.include_router(admin_router.router)     # /admin
app.include_router(threads_router.router)   # /threads
app.include_router(models_router.router)   # /models
app.include_router(workspace_router.router) # /workspace
app.include_router(agent_router.router)     # /agent

# 启动事件
@app.on_event("startup")
def startup():
    # 1. 确保工作空间根目录存在
    # 2. 确保管理员用户存在
    # 3. 确保默认模型配置存在
    # 4. 挂载前端静态文件（如果已构建）
```

### 2.2 数据模型

| 表名 | 模型类 | 说明 |
|------|--------|------|
| `users` | `User` | 用户信息，管理员标志 |
| `threads` | `Thread` | 对话线程，关联用户 |
| `runs` | `Run` | Agent 运行记录 |
| `global_api_keys` | `GlobalApiKey` | 加密的供应商 API 密钥 |
| `app_settings` | `AppSetting` | 应用设置（如默认模型） |
| `checkpoints` | `Checkpoint` | LangGraph 检查点数据 |
| `writes` | `Write` | LangGraph 检查点写入记录 |

### 2.3 核心模块

#### 2.3.1 认证模块 (`auth.py`)

```python
# 密码哈希 (PBKDF2)
hash_password(password: str) -> str
verify_password(password: str, hashed: str) -> bool

# JWT Token 生成
create_access_token(subject: str) -> str
create_refresh_token(subject: str) -> str
decode_token(token: str) -> dict | None
```

#### 2.3.2 Deep Agent 运行时 (`deep_agent_runtime.py`)

```python
def create_runtime(
    thread_id: str,
    workspace_path: str,
    model_id: str | None = None,
) -> Any:
    """创建 LangGraph Deep Agent 运行时实例"""
    model = _get_model_instance(model_id)
    checkpointer = MySQLSaver()
    backend = FilesystemBackend(root_dir=workspace_path, virtual_mode=True)

    system_prompt = build_system_prompt(workspace_path)
    execute_tool = make_execute_tool(workspace_path)

    agent = create_deep_agent(
        model=model,
        tools=[execute_tool],
        system_prompt=SystemMessage(content=system_prompt),
        backend=backend,
        checkpointer=checkpointer,
        interrupt_on={"execute": True},  # HITL 支持
    )
    return agent
```

#### 2.3.3 模型目录 (`model_catalog.py`)

支持的供应商和模型：

| 供应商 | ID | 模型示例 |
|--------|-----|----------|
| Anthropic | `anthropic` | Claude Opus 4.5, Claude Sonnet 4.5, Claude Haiku 4.5 |
| OpenAI | `openai` | GPT-5.2, GPT-5.1, o3, o3-mini, o4-mini |
| Google | `google` | Gemini 3 Pro, Gemini 3 Flash, Gemini 2.5 Pro |
| DeepSeek | `deepseek` | DeepSeek Chat, DeepSeek Reasoner |

默认模型: `claude-sonnet-4-5-20250929`

### 2.4 API 接口说明

#### 2.4.1 认证接口 (`/auth`)

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/auth/login` | 用户登录，返回 access_token 和 refresh_token (Cookie) |
| POST | `/auth/refresh` | 刷新 access_token |
| POST | `/auth/logout` | 登出，清除 Cookie |

**请求示例:**
```json
POST /auth/login
{
  "email": "admin@example.com",
  "password": "admin123"
}
```

#### 2.4.2 线程接口 (`/threads`)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/threads` | 获取当前用户的线程列表 |
| GET | `/threads/{thread_id}` | 获取单个线程详情 |
| POST | `/threads` | 创建新线程 |
| PATCH | `/threads/{thread_id}` | 更新线程标题、状态、元数据 |
| DELETE | `/threads/{thread_id}` | 删除线程及其检查点 |
| GET | `/threads/{thread_id}/history` | 获取线程历史（从检查点） |
| POST | `/threads/generate-title` | 根据消息生成线程标题 |

**ThreadOut 数据结构:**
```typescript
{
  thread_id: string
  user_id: string
  status: "idle" | "busy" | "interrupted" | "error"
  title?: string
  metadata?: Record<string, unknown>
  thread_values?: Record<string, unknown>
  created_at: Date
  updated_at: Date
}
```

#### 2.4.3 模型接口 (`/models`)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/models` | 获取可用模型列表 |
| GET | `/models/providers` | 获取供应商列表（含 API 密钥状态） |
| GET | `/models/default` | 获取默认模型 ID |
| POST | `/models/default` | 设置默认模型（管理员） |
| POST | `/models/api-key` | 设置供应商 API 密钥（管理员） |
| DELETE | `/models/api-key/{provider}` | 删除供应商 API 密钥（管理员） |
| GET | `/models/api-key/{provider}` | 获取供应商 API 密钥（管理员） |

#### 2.4.4 工作空间接口 (`/workspace`)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/workspace` | 获取工作空间路径 |
| GET | `/workspace/files` | 列出工作空间文件 |
| GET | `/workspace/file` | 读取文本文件内容 |
| GET | `/workspace/file-binary` | 读取二进制文件（Base64） |
| POST | `/workspace/sync` | 将检查点文件同步到磁盘 |
| GET | `/workspace/changes` | SSE 监听文件变更 |

#### 2.4.5 Agent 流式接口 (`/agent`)

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/agent/stream` | SSE 流式 Agent 响应 |

**请求:**
```json
{
  "thread_id": "string",
  "message": "string",
  "model_id": "string | null",
  "command": { "resume": any } | null
}
```

**SSE 事件:**
```javascript
// 流式消息
data: {"type": "stream", "mode": "messages", "data": [...]}

// 状态更新
data: {"type": "stream", "mode": "values", "data": {...}}

// 完成
data: {"type": "done"}

// 错误
data: {"type": "error", "error": "error message"}
```

### 2.5 依赖注入 (`deps.py`)

```python
def get_db() -> Generator[Session, None, None]
    # 数据库会话依赖

def get_current_user(request: Request, db: Session) -> User
    # 从 Cookie 解析 JWT，获取当前用户

def require_admin(user: User = Depends(get_current_user)) -> User
    # 要求管理员权限
```

---

## 3. 前端架构 (Web)

### 3.1 应用结构

入口: `web/src/App.tsx`

```
App
├── ThreadProvider (线程上下文)
│   ├── ThreadSidebar (左侧线程列表)
│   ├── TabBar / KanbanHeader (标题栏)
│   ├── TabbedPanel / KanbanView (主内容区)
│   └── RightPanel (右侧面板)
```

### 3.2 状态管理

#### 3.2.1 Zustand 全局状态 (`store.ts`)

```typescript
interface AppState {
  // 线程
  threads: Thread[]
  currentThreadId: string | null

  // 模型和供应商（全局）
  models: ModelConfig[]
  providers: Provider[]

  // UI 状态
  rightPanelTab: "todos" | "files" | "subagents"
  settingsOpen: boolean
  sidebarCollapsed: boolean
  showKanbanView: boolean
  showSubagentsInKanban: boolean

  // 操作方法
  loadThreads: () => Promise<void>
  createThread: (metadata?: Record<string, unknown>) => Promise<Thread>
  selectThread: (threadId: string) => Promise<void>
  deleteThread: (threadId: string) => Promise<void>
  updateThread: (threadId: string, updates: Partial<Thread>) => Promise<void>

  loadModels: () => Promise<void>
  loadProviders: () => Promise<void>
  setApiKey: (providerId: string, apiKey: string) => Promise<void>
  deleteApiKey: (providerId: string) => Promise<void>
  // ...
}
```

#### 3.2.2 线程上下文 (`thread-context.tsx`)

```typescript
interface ThreadState {
  messages: Message[]
  todos: Todo[]
  workspaceFiles: FileInfo[]
  workspacePath: string | null
  subagents: Subagent[]
  pendingApproval: HITLRequest | null
  error: string | null
  currentModel: string
  openFiles: OpenFile[]
  activeTab: "agent" | string
  fileContents: Record<string, string>
  tokenUsage: TokenUsage | null
  draftInput: string
}

// Hooks
useThreadContext()          // 获取上下文
useCurrentThread(threadId)  // 获取当前线程状态和操作
useThreadStream(threadId)   // 订阅流数据
useAllThreadStates()        // 获取所有线程状态（看板用）
```

### 3.3 组件目录

#### 3.3.1 聊天组件 (`components/chat/`)

| 组件 | 说明 |
|------|------|
| `ChatContainer.tsx` | 聊天容器，消息输入/显示 |
| `MessageBubble.tsx` | 消息气泡渲染 |
| `StreamingMarkdown.tsx` | 流式 Markdown 渲染 |
| `ToolCallRenderer.tsx` | 工具调用结果渲染 |
| `ChatTodos.tsx` | 聊天内联 TODO 列表 |
| `ModelSwitcher.tsx` | 模型选择器 |
| `WorkspacePicker.tsx` | 工作空间选择器 |
| `ApiKeyDialog.tsx` | API 密钥输入对话框 |
| `ContextUsageIndicator.tsx` | Token 使用量指示器 |

#### 3.3.2 侧边栏 (`components/sidebar/`)

| 组件 | 说明 |
|------|------|
| `ThreadSidebar.tsx` | 线程列表侧边栏 |

#### 3.3.3 面板 (`components/panels/`)

| 组件 | 说明 |
|------|------|
| `RightPanel.tsx` | 右侧面板容器 |
| `TodoPanel.tsx` | TODO 面板 |
| `FilesystemPanel.tsx` | 文件系统面板 |
| `SubagentPanel.tsx` | 子代理面板 |

#### 3.3.4 标签页 (`components/tabs/`)

| 组件 | 说明 |
|------|------|
| `TabBar.tsx` | 标签栏 |
| `TabbedPanel.tsx` | 标签页内容容器 |
| `FileViewer.tsx` | 文件查看器（路由不同类型） |
| `CodeViewer.tsx` | 代码查看器（语法高亮） |
| `ImageViewer.tsx` | 图片查看器 |
| `PDFViewer.tsx` | PDF 查看器 |
| `BinaryFileViewer.tsx` | 二进制文件查看器 |
| `MediaViewer.tsx` | 音视频查看器 |

#### 3.3.5 看板 (`components/kanban/`)

| 组件 | 说明 |
|------|------|
| `KanbanView.tsx` | 看板视图主容器 |
| `KanbanHeader.tsx` | 看板标题栏 |
| `KanbanColumn.tsx` | 看板列 |
| `KanbanCard.tsx` | 看板卡片（线程/子代理） |

#### 3.3.6 基础 UI (`components/ui/`)

Radix UI 封装组件：
- `button.tsx` - 按钮
- `input.tsx` - 输入框
- `dialog.tsx` - 对话框
- `popover.tsx` - 弹出框
- `scroll-area.tsx` - 滚动区域
- `resizable.tsx` - 可调整大小面板
- `context-menu.tsx` - 右键菜单
- `separator.tsx` - 分隔线
- `badge.tsx` - 徽章
- `card.tsx` - 卡片

### 3.4 类型定义 (`types.ts`)

```typescript
// 线程
type ThreadStatus = "idle" | "busy" | "interrupted" | "error"

interface Thread {
  thread_id: string
  created_at: Date
  updated_at: Date
  metadata?: Record<string, unknown>
  status: ThreadStatus
  title?: string
}

// 消息
interface Message {
  id: string
  role: "user" | "assistant" | "system" | "tool"
  content: string | ContentBlock[]
  tool_calls?: ToolCall[]
  tool_call_id?: string
  name?: string
  created_at: Date
}

// 流事件
type StreamEvent =
  | { type: "message"; message: Message }
  | { type: "tool_call"; toolCall: ToolCall }
  | { type: "tool_result"; toolResult: ToolResult }
  | { type: "interrupt"; request: HITLRequest }
  | { type: "token"; token: string }
  | { type: "todos"; todos: Todo[] }
  | { type: "workspace"; files: FileInfo[]; path: string }
  | { type: "subagents"; subagents: Subagent[] }
  | { type: "done"; result: unknown }
  | { type: "error"; error: string }

// 子代理
interface Subagent {
  id: string
  name: string
  description: string
  status: "pending" | "running" | "completed" | "failed"
  startedAt?: Date
  completedAt?: Date
  toolCallId?: string
  subagentType?: string
}
```

### 3.5 Window API 注入 (`window-api.ts`)

为了兼容 Electron IPC，通过 `attachWindowApi()` 注入 `window.api`：

```typescript
// 认证
window.api.auth.login(email, password)
window.api.auth.logout()
window.api.auth.refresh()

// 线程
window.api.threads.list()
window.api.threads.get(threadId)
window.api.threads.create(metadata)
window.api.threads.update(threadId, updates)
window.api.threads.delete(threadId)
window.api.threads.getHistory(threadId)
window.api.threads.generateTitle(message)

// 模型
window.api.models.list()
window.api.models.listProviders()
window.api.models.getDefault()
window.api.models.setDefault(modelId)
window.api.models.setApiKey(provider, apiKey)
window.api.models.deleteApiKey(provider)

// 工作空间
window.api.workspace.get()
window.api.workspace.loadFromDisk(threadId)
window.api.workspace.readFile(threadId, path)
window.api.workspace.readBinaryFile(threadId, path)
window.api.workspace.syncToDisk(threadId)
window.api.workspace.onFilesChanged(callback)

// Agent
window.api.agent.streamAgent(threadId, message, command, onEvent, modelId)
window.api.agent.cancel(threadId)
```

---

## 4. 开发指南

### 4.1 环境配置

**后端配置** (`server/config.yaml`):
```yaml
database:
  url: "mysql+pymysql://user:pass@host:3306/openwork"
auth:
  jwt_secret: "CHANGE_ME"
  access_ttl_min: 60
  refresh_ttl_days: 7
workspace:
  root: "/var/lib/openwork/workspaces"
data:
  dir: "/var/lib/openwork"
admin:
  email: "admin@example.com"
  password: "admin123"
```

**前端配置** (环境变量):
```bash
# 开发环境自动检测
# http://localhost:5173 -> http://localhost:8000
# http://127.0.0.1:5176 -> http://127.0.0.1:8000

# 或手动指定
VITE_API_BASE_URL=http://localhost:8000
```

### 4.2 启动开发服务器

**后端:**
```bash
cd server
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**前端:**
```bash
cd web
npm run dev
```

### 4.3 数据库迁移

```bash
cd server
alembic upgrade head
```

### 4.4 添加新模型

编辑 `server/app/model_catalog.py`:

```python
MODELS = [
    ModelConfig(
        id="model-id",
        name="Model Name",
        provider="provider-id",
        model="actual-model-name",
        description="Description",
        available=True,
    ),
    # ...
]
```

### 4.5 添加新 API 路由

1. 在 `server/app/api/` 创建新模块
2. 定义 `APIRouter` 并添加路由
3. 在 `main.py` 中注册路由

```python
# server/app/api/example.py
from fastapi import APIRouter, Depends

router = APIRouter(prefix="/example", tags=["example"])

@router.get("")
def get_example(user: User = Depends(get_current_user)):
    return {"message": "Hello"}

# main.py
from .api import example as example_router
app.include_router(example_router.router)
```

### 4.6 添加前端组件

1. 在 `web/src/components/` 创建组件文件
2. 导出组件
3. 在需要的地方引入使用

```typescript
// web/src/components/example/Example.tsx
export function Example(): React.JSX.Element {
  return <div>Example Component</div>
}
```

---

## 5. 设计系统

### 5.1 SCADA/Tactical 风格

- **主题**: 深色模式
- **字体**: JetBrains Mono (等宽)
- **间距**: 4px 增量
- **圆角**: 统一 3px

### 5.2 颜色变量

| 变量 | 用途 |
|------|------|
| `--background` | 背景色 |
| `--foreground` | 前景色 |
| `--card` | 卡片背景 |
| `--card-foreground` | 卡片前景 |
| `--popover` | 弹出框背景 |
| `--primary` | 主色 |
| `--primary-foreground` | 主色前景 |
| `--secondary` | 次要色 |
| `--muted` | 静音色 |
| `--accent` | 强调色 |
| `--destructive` | 危险/错误 |
| `--border` | 边框 |
| `--input` | 输入框 |
| `--ring` | 焦点环 |

### 5.3 状态颜色

| 状态 | 颜色 | 用途 |
|------|------|------|
| Nominal | 绿色 | 正常状态 |
| Warning | 黄色 | 警告状态 |
| Critical | 红色 | 错误/中断状态 |
| Info | 蓝色 | 信息提示 |

---

## 6. 部署

### 6.1 后端部署

```bash
cd server
uv sync --no-dev
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### 6.2 前端构建

```bash
cd web
npm run build
# 产出: web/dist/
```

后端启动时会自动挂载 `web/dist` 作为静态文件服务。

### 6.3 生产环境配置

1. 修改 `config.yaml` 中的数据库连接
2. 设置强密码和 JWT 密钥
3. 配置反向代理 (Nginx) 处理 HTTPS
4. 配置工作空间目录权限

---

*文档版本: 1.0.0*
*更新时间: 2025-02-01*
