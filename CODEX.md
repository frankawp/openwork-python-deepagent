# CODEX.md

This file provides guidance to Codex CLI when working with code in this repository.

## 项目概述

openwork 是 [deepagentsjs](https://github.com/langchain-ai/deepagentsjs) 的桌面界面，提供具有文件系统访问能力、任务规划和子代理委托功能的 AI 智能体界面。

项目正在从 Electron 桌面应用重构为 BS（Browser-Server）架构：
- **server/** - FastAPI Python 后端
- **web/** - React TypeScript 前端
- **src/** - 原有 Electron 应用（仍在维护）

---

## Server（Python 后端）

### 技术栈
- Python 3.10+
- FastAPI + Uvicorn
- SQLAlchemy ORM + MySQL
- Alembic 数据库迁移
- LangGraph 检查点存储

### 启动服务器
```bash
cd server
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 配置
服务器通过 `server/config.yaml` 配置，首次运行需复制 `config.example.yaml`：

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

### API 路由结构
- `/auth` - JWT 认证（登录、登出、刷新 token）
- `/admin` - 管理功能
- `/threads` - 线程 CRUD 操作
- `/models` - 模型配置和 API 密钥管理
- `/workspace` - 文件系统操作
- `/agent` - AI 智能体流式响应（SSE）

### 数据库模型
- **User** - 用户信息，管理员标志
- **Thread** - 对话线程，关联用户
- **Run** - 智能体运行记录
- **GlobalApiKey** - 加密的供应商 API 密钥
- **AppSetting** - 应用设置（如默认模型）
- **Checkpoint/Write** - LangGraph 检查点表

---

## Web（React 前端）

### 技术栈
- React 19.2.1 + TypeScript 5.9.3
- Vite 7.2.6 构建工具
- Radix UI 组件 + Tailwind CSS 4.0
- Zustand 状态管理

### 启动前端
```bash
cd web
npm run dev      # 开发服务器
npm run build    # 构建生产版本
npm run preview  # 预览构建结果
```

### 状态管理
使用 Zustand (`web/src/lib/store.ts`)，管理：
- 线程列表和当前选中线程
- 全局模型配置和供应商
- UI 状态（面板、侧边栏、看板视图）

### API 通信
- RESTful API 通过 `window.api.*` 调用
- Server-Sent Events (SSE) 用于 AI 流式响应
- EventSource 用于文件变更监听

### 组件结构
- `components/chat/` - 聊天界面、消息气泡、工具调用渲染
- `components/sidebar/` - 线程侧边栏
- `components/panels/` - 右侧面板（Todo、文件系统、子代理）
- `components/kanban/` - 看板视图
- `components/tabs/` - 多标签页文件查看器
- `components/ui/` - Radix UI 封装组件

---

## 桌面应用（Electron）

### 启动开发服务器
```bash
npm run dev    # electron-vite 开发模式
npm run build  # 类型检查 + 构建
npm run start  # 预览打包后的应用
npm run lint   # ESLint 检查
npm run format # Prettier 格式化
```

---

## 设计系统

项目采用 **tactical/SCADA 风格**：
- **颜色**：深色主题，状态颜色（critical/warning/nominal/info）
- **字体**：JetBrains Mono
- **间距**：4px 增量，3px 圆角
- **圆角**：统一 3px

---

## 智能体架构

- 使用 LangGraph 进行工作流管理
- 支持子代理（Subagent）模式
- 人机交互（HITL）机制
- 多模型支持：Anthropic、OpenAI、Google、DeepSeek

---

## 数据库迁移

```bash
cd server
alembic upgrade head
```

迁移文件位于 `server/alembic/versions/`。
