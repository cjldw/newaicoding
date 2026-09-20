# 开发计划:AI Web 开发平台

> PRD:./PRD.md
> ARCH:./ARCH.md
> 创建日期:2026-09-21
> 状态:**已确认**

## 需求概述

从零搭建一个**AI 驱动的研发流程协作平台**,覆盖**需求打磨 → 开发 → 测试 → 发布 → 归档**全流程;17 个需求点(R1–R17),7 个模块(M1–M7),全部新建,无历史代码包袱。

**核心技术栈**(按 ARCH 决策):
- **后端**:Python 3.12 + FastAPI + SQLAlchemy 2.0 async + MySQL 8.0 + asyncmy
- **前端**:React 18 + Vite + TypeScript + Tailwind + shadcn/ui + Zustand + react-query
- **容器**:基于 `mcr.microsoft.com/devcontainer/universal:linux` + Claude CLI;Runner 架构(多机器)
- **AI**:Claude Agent SDK 主路径 + 容器内 Claude CLI 兜底
- **Git**:GitLab + python-gitlab + HTTPS clone + 用户个人 token
- **加密**:AES-256-GCM + 环境变量密钥

**设计规范**:**shadcn/ui (New York)**(DESIGN.md)——中性、精致、微妙的边框与 ring;小圆角(0.5rem);柔和的 zinc/slate 色板;可访问 Radix 原语。

## 技术约定

### 后端约定(按 ARCH D1/D2/D3/D4/D6/D7/D9 决策)

| 类别 | 选型 | 说明 |
|---|---|---|
| **语言** | Python 3.12 | 按 D1 |
| **框架** | FastAPI | 按 D1;自带 OpenAPI 文档;asyncio 原生支持 WebSocket/SSE |
| **异步** | asyncio + uvloop | 按 D1;uvloop 提升性能 |
| **ORM** | SQLAlchemy 2.0(async) | 按 D2;`asyncmy` 驱动 |
| **数据库** | MySQL 8.0 | 按 D2;JSON 字段用 `JSON` 类型;行级锁 `SELECT ... FOR UPDATE` |
| **DB 迁移** | alembic | SQLAlchemy 官方迁移工具 |
| **AI SDK** | `claude-agent-sdk` (Python) | 按 D3;主路径;容器内 Claude CLI 兜底 |
| **GitLab** | `python-gitlab` | 按 D4;官方推荐客户端 |
| **Git 操作** | 系统 `git` 命令 + HTTPS clone | 按 D4;token 通过 `git credential.helper` 注入 |
| **HTTP 客户端** | `httpx`(async) | FastAPI 官方推荐 |
| **JWT** | `pyjwt` | 轻量 |
| **密码哈希** | `passlib[bcrypt]` | 统一接口,便于未来换 argon2 |
| **加密** | `cryptography` (AES-256-GCM) | 按 D9;密钥从环境变量 `PLATFORM_SECRET_KEY` 读 |
| **容器编排** | Runner 架构(不直接调 Docker) | 按 D6;Runner 主动 WebSocket 连接平台;Runner 本地调 Docker SDK |
| **任务调度** | MySQL 行级锁 + asyncio.Queue | 按 D7;单实例够用 |
| **测试** | `pytest` + `pytest-asyncio` + `pytest-cov` + `httpx.AsyncClient` | |
| **代码质量** | `ruff`(lint+format) + `mypy` | ruff 是 Rust 写的,快 100 倍 |

**目录结构**(后端):
```
backend/
├── app/
│   ├── main.py                 # FastAPI 入口
│   ├── config.py               # 配置(pydantic-settings)
│   ├── database.py             # SQLAlchemy async engine + session
│   ├── models/                 # SQLAlchemy 模型
│   │   ├── user.py
│   │   ├── project.py
│   │   ├── requirement.py
│   │   ├── task.py
│   │   ├── container.py
│   │   ├── runner.py
│   │   └── ...
│   ├── schemas/                # Pydantic 模型(请求/响应)
│   ├── api/                    # API 路由
│   │   ├── auth.py
│   │   ├── users.py
│   │   ├── projects.py
│   │   ├── requirements.py
│   │   ├── tasks.py
│   │   ├── admin/
│   │   │   ├── runners.py
│   │   │   ├── platform_settings.py
│   │   │   └── ...
│   │   └── webhooks/
│   │       └── gitlab.py
│   ├── services/               # 业务逻辑
│   │   ├── auth_service.py
│   │   ├── gitlab_service.py
│   │   ├── claude_service.py
│   │   ├── runner_service.py
│   │   ├── container_service.py
│   │   └── ...
│   ├── core/                   # 核心组件
│   │   ├── security.py         # JWT/密码/AES-GCM
│   │   ├── websocket.py        # WebSocket 网关(D5)
│   │   ├── task_scheduler.py   # 任务调度(D7)
│   │   └── encryption.py       # AES-GCM
│   └── utils/
├── alembic/                    # DB 迁移
├── tests/
├── pyproject.toml
└── README.md
```

**请求封装与统一错误处理**:
- 所有 API 路由返回 `{"code": 0, "data": ..., "message": "ok"}` 或 `{"code": 1001, "message": "错误信息"}`
- 全局异常处理器:`@app.exception_handler(Exception)` 捕获所有异常,返回统一格式
- 鉴权:`Depends(get_current_user)` 依赖注入;JWT 从 `Authorization: Bearer {token}` 头读

### 前端约定(按 ARCH D8 决策)

| 类别 | 选型 | 说明 |
|---|---|---|
| **框架** | React 18 + Vite + TypeScript | 按 D8 |
| **样式** | Tailwind CSS + shadcn/ui | 按 D8 + DESIGN.md |
| **状态管理** | Zustand(本地) + react-query(服务端) | 按 D8 |
| **路由** | react-router-dom v6 | |
| **表单** | react-hook-form + zod | |
| **Markdown** | `react-markdown` + `remark-gfm` | |
| **编辑器** | `@monaco-editor/react` | 按 D11 |
| **终端** | `xterm` + `xterm-addon-fit` + `xterm-addon-web-links` | 按 D11;**不用** `xterm-for-react`(已停止维护) |
| **Diff 视图** | `react-diff-viewer-continued` | |
| **图标** | `lucide-react` | **不用 emoji** |

**目录结构**(前端):
```
frontend/
├── src/
│   ├── main.tsx
│   ├── App.tsx
│   ├── router.tsx              # react-router 路由配置
│   ├── pages/                  # 页面
│   │   ├── auth/
│   │   │   ├── Login.tsx
│   │   │   └── Register.tsx
│   │   ├── projects/
│   │   │   ├── ProjectList.tsx
│   │   │   ├── ProjectDetail.tsx
│   │   │   └── ProjectSettings.tsx
│   │   ├── requirements/
│   │   │   ├── RequirementList.tsx
│   │   │   ├── RequirementDetail.tsx
│   │   │   └── RequirementCreate.tsx
│   │   ├── tasks/
│   │   │   ├── TaskDetail.tsx          # 任务工作台
│   │   │   └── TaskCreate.tsx
│   │   ├── knowledge/
│   │   │   └── KnowledgeBase.tsx
│   │   └── admin/
│   │       ├── PlatformSettings.tsx
│   │       ├── RunnerManagement.tsx
│   │       └── UserManagement.tsx
│   ├── components/             # 通用组件
│   │   ├── ui/                 # shadcn/ui 组件(button/input/card/...)
│   │   ├── Terminal.tsx        # xterm.js 封装
│   │   ├── Editor.tsx          # Monaco 封装
│   │   ├── DiffViewer.tsx      # diff 视图
│   │   ├── FileTree.tsx        # 文件树
│   │   └── ...
│   ├── stores/                 # Zustand stores
│   │   ├── authStore.ts
│   │   ├── projectStore.ts
│   │   └── ...
│   ├── api/                    # API 客户端(react-query)
│   │   ├── client.ts           # axios/fetch 封装
│   │   ├── auth.ts
│   │   ├── projects.ts
│   │   └── ...
│   ├── hooks/                  # 自定义 hooks
│   ├── utils/
│   └── styles/
│       └── globals.css         # Tailwind + DESIGN.md tokens
├── public/
├── package.json
├── tsconfig.json
├── vite.config.ts
└── tailwind.config.ts
```

**状态管理约定**:
- **服务端状态**(项目列表/需求列表/任务详情):react-query(`useQuery` / `useMutation`)
- **本地状态**(当前打开的文件/终端 Tab/编辑器状态):Zustand
- **表单状态**:react-hook-form + zod 校验

### 设计规范(DESIGN.md,shadcn/ui New York)

**全局 CSS 变量**(`frontend/src/styles/globals.css`):

```css
@import url('https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600;700&family=Geist+Mono&display=swap');

@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {
  :root {
    /* color: zinc palette, "New York" preset */
    --color-bg: #ffffff;
    --color-surface: #ffffff;
    --color-surface-strong: #f4f4f5;
    --color-border: #e4e4e7;
    --color-text: #09090b;
    --color-text-muted: #71717a;
    --color-primary: #18181b;
    --color-accent: #2563eb;
    --color-ring: #a1a1aa;

    /* radius */
    --radius-sm: 0.375rem;
    --radius-md: 0.5rem;
    --radius-lg: 0.75rem;
    --radius-pill: 999px;

    /* shadow: very subtle, never decorative */
    --shadow-sm: 0 1px 2px rgba(0,0,0,0.04);
    --shadow-md: 0 1px 3px rgba(0,0,0,0.08), 0 1px 2px rgba(0,0,0,0.04);
    --shadow-lg: 0 10px 15px rgba(0,0,0,0.08), 0 4px 6px rgba(0,0,0,0.05);

    /* font */
    --font-sans: 'Geist', 'Inter', system-ui, -apple-system, sans-serif;
    --font-display: 'Geist', 'Inter', system-ui, sans-serif;
    --font-mono: 'Geist Mono', ui-monospace, 'SFMono-Regular', monospace;

    /* text */
    --text-xs: 0.75rem;
    --text-sm: 0.875rem;
    --text-base: 1rem;
    --text-lg: 1.125rem;
    --text-xl: 1.375rem;
    --text-2xl: 1.75rem;
    --text-3xl: 2.25rem;
    --text-4xl: 3rem;
    --text-5xl: 4rem;

    /* space */
    --space-1: 4px;
    --space-2: 8px;
    --space-3: 12px;
    --space-4: 16px;
    --space-6: 24px;
    --space-8: 32px;
    --space-12: 48px;
    --space-16: 64px;
    --space-24: 96px;

    /* ease */
    --ease-standard: cubic-bezier(0.16, 1, 0.3, 1);

    /* signature move: two-layer focus ring */
    --ring-offset: 0 0 0 2px var(--color-bg);
    --ring: 0 0 0 4px color-mix(in srgb, var(--color-ring) 35%, transparent);
  }
}

@layer components {
  /* shadcn/ui (New York) signature styles */
  .btn {
    @apply font-medium text-sm px-4 py-2 rounded-md bg-surface border border-border shadow-sm cursor-pointer transition-all;
  }
  .btn:hover { @apply bg-surface-strong; }
  .btn:active { @apply bg-[#ececef]; }
  .btn:focus-visible { @apply outline-none; box-shadow: var(--ring-offset), var(--ring); }
  .btn[disabled] { @apply opacity-50 cursor-not-allowed; }

  .btn--primary { @apply bg-primary text-white border-primary; }
  .btn--primary:hover { @apply bg-[#27272a]; }

  .card { @apply bg-surface text-text border border-border rounded-lg shadow-sm p-6; }

  .input { @apply w-full box-border text-text text-sm px-3 py-2 bg-surface border border-border rounded-md; }
  .input::placeholder { @apply text-text-muted; }
  .input:focus { @apply outline-none border-ring; box-shadow: var(--ring-offset), var(--ring); }

  .badge { @apply inline-flex items-center gap-1 font-semibold text-xs px-2 py-1 rounded-pill bg-surface-strong border border-border text-text; }
}

@layer base {
  body { @apply m-0 text-text font-sans bg-bg; }

  @media (prefers-reduced-motion: reduce) {
    .btn { @apply transition-none; }
  }
}
```

**Tailwind 配置**(`frontend/tailwind.config.ts`):

```typescript
import type { Config } from 'tailwindcss'

export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        bg: 'var(--color-bg)',
        surface: 'var(--color-surface)',
        'surface-strong': 'var(--color-surface-strong)',
        border: 'var(--color-border)',
        text: 'var(--color-text)',
        'text-muted': 'var(--color-text-muted)',
        primary: 'var(--color-primary)',
        accent: 'var(--color-accent)',
        ring: 'var(--color-ring)',
      },
      borderRadius: {
        sm: 'var(--radius-sm)',
        md: 'var(--radius-md)',
        lg: 'var(--radius-lg)',
        pill: 'var(--radius-pill)',
      },
      boxShadow: {
        sm: 'var(--shadow-sm)',
        md: 'var(--shadow-md)',
        lg: 'var(--shadow-lg)',
      },
      fontFamily: {
        sans: 'var(--font-sans)',
        display: 'var(--font-display)',
        mono: 'var(--font-mono)',
      },
      fontSize: {
        xs: 'var(--text-xs)',
        sm: 'var(--text-sm)',
        base: 'var(--text-base)',
        lg: 'var(--text-lg)',
        xl: 'var(--text-xl)',
        '2xl': 'var(--text-2xl)',
        '3xl': 'var(--text-3xl)',
        '4xl': 'var(--text-4xl)',
        '5xl': 'var(--text-5xl)',
      },
      spacing: {
        '1': 'var(--space-1)',
        '2': 'var(--space-2)',
        '3': 'var(--space-3)',
        '4': 'var(--space-4)',
        '6': 'var(--space-6)',
        '8': 'var(--space-8)',
        '12': 'var(--space-12)',
        '16': 'var(--space-16)',
        '24': 'var(--space-24)',
      },
      transitionTimingFunction: {
        standard: 'var(--ease-standard)',
      },
    },
  },
  plugins: [],
} satisfies Config
```

**组件规范**(shadcn/ui New York):
- **按钮**:`.btn`(默认)/ `.btn--primary`(主按钮);统一 0.5rem 圆角 + 1px hairline 边框 + 双层 focus ring
- **卡片**:`.card`;`rounded-lg`(0.75rem)+ `shadow-sm` + `p-6`
- **输入框**:`.input`;聚焦时双层 ring + `border-ring`
- **徽章**:`.badge`;`rounded-pill` + `bg-surface-strong` + `text-xs`
- **图标**:`lucide-react`(**不用 emoji**);尺寸 `w-4 h-4`(默认)/ `w-5 h-5`(大)
- **可访问性**:WCAG AA 对比度;所有交互元素可见 focus;键盘导航;`prefers-reduced-motion`

### 容器镜像(按 ARCH D10 决策)

**Dockerfile**(`docker/devbox/Dockerfile`):

```dockerfile
FROM mcr.microsoft.com/devcontainer/universal:linux

USER root

# Claude CLI
RUN npm install -g @anthropic-ai/claude-code

# 预装高频 Python 包
RUN pip3 install --break-system-packages \
    fastapi uvicorn sqlalchemy pytest requests httpx

# 预装高频 npm 包
RUN npm install -g vite create-react-app

# 预装常用 MCP server(按 D15)
RUN npm install -g \
    @modelcontextprotocol/server-filesystem \
    @modelcontextprotocol/server-git \
    @modelcontextprotocol/server-github \
    @modelcontextprotocol/server-sqlite \
    @modelcontextprotocol/server-brave-search

# 预装平台官方 Skills(按 D15)
COPY skills/ /home/codespace/.claude/skills/

USER codespace
WORKDIR /workspace
CMD ["/bin/bash"]
```

**环境变量注入**(任务创建时,按 D10):
- `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL`(通用)
- `ANTHROPIC_BASE_URL` / `ANTHROPIC_API_KEY`(Claude CLI 兼容)
- `GITLAB_TOKEN` / `GITLAB_INSTANCE_URL` / `GIT_USER_NAME` / `GIT_USER_EMAIL`
- `TASK_ID` / `PROJECT_ID` / `REQ_ID`

**git credential.helper 配置**(容器启动脚本):
```bash
git config --global credential.helper '!f() { echo "username=oauth2"; echo "password=${GITLAB_TOKEN}"; }; f'
git config --global user.name "${GIT_USER_NAME}"
git config --global user.email "${GIT_USER_EMAIL}"
```

### Runner 架构(按 ARCH D6/D13/D14 决策)

**Runner 镜像**(`docker/runner/Dockerfile`):

```dockerfile
FROM python:3.12-slim

RUN pip3 install fastapi uvicorn websockets docker asyncio

COPY runner/ /app/

WORKDIR /app
CMD ["python3", "main.py"]
```

**Runner 启动**:
```bash
docker run -d \
  -e PLATFORM_URL=wss://platform.example.com/ws/runner \
  -e RUNNER_TOKEN=xxx \
  -v /var/run/docker.sock:/var/run/docker.sock \
  --name runner-01 \
  platform/runner:v1
```

**Runner 与平台通信**(按 D13):
- WebSocket 长连接
- 消息协议:JSON,`{"type": "register|heartbeat|start_container|stop_container|exec|...", ...}`
- 心跳:Runner 每 30s 发 `ping`;平台 60s 未收到标记 offline

**Runner 上的本地代理**(按 D14):
- Runner 机器上跑 Nginx,把容器端口暴露给 Runner 的某个端口
- Runner 启动容器时分配随机宿主机端口(范围 20000-29999),配置 Nginx 转发到该端口
- 平台网关转发到 Runner 的 Nginx 端口,再到容器

## 当前进度

**当前进度: 0/18 (0%) - 未开始**

| 需求点 | 名称 | 模块 | 状态 | 详情文件 |
|---|---|---|---|---|
| R1 | 用户与账号体系 | M1 | ⬜ | ./DEVPLAN/R1.md |
| R2 | 项目管理(多仓库) | M1 | ⬜ | ./DEVPLAN/R2.md |
| R12 | 项目成员与协作 | M1 | ⬜ | ./DEVPLAN/R12.md || R13 | 模型接入 | M3 | ⬜ | ./DEVPLAN/R13.md |
| R17 | MCP server 与 Skills 管理 | M3 | ⬜ | ./DEVPLAN/R17.md |
| R8 | 任务级容器 | M5 | ⬜ | ./DEVPLAN/R8.md |
| R16 | Runner 管理 | M5 | ⬜ | ./DEVPLAN/R16.md |
| R9 | Web 终端 | M5 | ⬜ | ./DEVPLAN/R9.md |
| R10 | 实时预览 | M5 | ⬜ | ./DEVPLAN/R10.md |
| R11 | 在线编辑器 | M5 | ⬜ | ./DEVPLAN/R11.md |
| R15 | 平台网关与域名 | M6 | ⬜ | ./DEVPLAN/R15.md |
| R3 | 需求管理与打磨 | M4 | ⬜ | ./DEVPLAN/R3.md |
| R4 | 任务(统一执行单元) | M4 | ⬜ | ./DEVPLAN/R4.md |
| R5 | 开发任务 | M4 | ⬜ | ./DEVPLAN/R5.md |
| R6 | 测试任务 | M4 | ⬜ | ./DEVPLAN/R6.md |
| R7 | 发布任务 | M4 | ⬜ | ./DEVPLAN/R7.md |
| R14 | 归档与知识库 | M7 | ⬜ | ./DEVPLAN/R14.md |
| R18 | 站内信与通知 | M8 | ⬜ | ./DEVPLAN/R18.md |

(状态:⬜ 未开始 / 🔄 进行中 / ✅ 完成 / ⚠️ 有问题。这张表是**全流程唯一的续接入口**——清上下文后只读它定位,再按需读详情文件,不全量重读)

## 模块拆分与时间线

| 模块 | 包含需求点 | 依赖 | 预计耗时 | 顺序 |
|---|---|---|---|---|
| **M1 基础设施** | R1(用户/账号), R2(项目/多仓库), R12(协作/权限) | - | 5d | 1 |
| **M2 平台设置** | (隐含)平台设置(GitLab/Runner 管理) | M1 | 2d | 2 |
| **M3 AI 能力** | R13(模型接入), R17(MCP server + Skills) | M1 | 3d | 3 |
| **M5 执行环境** | R8(容器), R16(Runner), R9(终端), R10(预览), R11(编辑器) | M1, M3 | 8d | 4 |
| **M6 网关与路由** | R15(网关) | M5 | 3d | 5 |
| **M4 流程引擎** | R3(需求), R4(任务), R5(开发), R6(测试), R7(发布) | M1, M3, M5, M6 | 10d | 6 |
| **M7 归档与知识库** | R14 | M4 | 3d | 7 |
| **M8 通知** | R18(站内信与通知) | M1, M4, M5 | 2d | 8 |

(依赖顺序即推荐开发顺序;无依赖的模块可并行)

**总耗时**:34 天(约 7 周,1 人);多人并行可压缩到 3-4 周。

## 业务旅程(跨需求点)

| 旅程 | 链路(需求点顺序) | 关键数据传导 |
|---|---|---|
| **J1 需求全流程** | R3(需求) → R4(任务) → R5(开发) → R6(测试) → R7(发布) → R14(归档) | R3 的 PRD 被 R5/R6 消费;R6 的报告被 R7 携带;R7 的产物被 R14 归档 |
| **J2 用户接入流程** | R1(注册/绑定 GitLab token)→ R12(被邀请加入项目)→ R3(创建需求) | R1 的 token 被 R12/R3/R4 使用 |
| **J3 平台初始化流程** | M2(平台设置:GitLab/Runner)→ R2(创建项目)→ R3(创建需求) | M2 的 GitLab token 被 R2 使用;Runner token 被 R16 使用 |
| **J4 文件协作流程** | R4(任务) → 文件上传 → `@文件` 引用 → AI 处理 → R11(编辑器查看变更) | R4 的上传文件被 AI 消费;R11 查看 AI 改动 |
| **J5 容器执行流程** | R4(任务) → R16(Runner 调度) → R8(容器拉起) → R9(终端) / R10(预览) / R11(编辑器) | R16 分配 Runner;R8 拉起容器;R9/R10/R11 共用容器 |

## 范围外

(从 PRD"范围外"摘录)

- 桌面客户端 / 移动端 / 浏览器插件
- 第三方登录(OAuth/SSO/手机号)
- 组织/团队层级
- GitHub / Gitee 等其他 Git 托管(V1 仅 GitLab)
- 自定义容器镜像 / docker-compose / SSH 直连
- 宿主机挂载持久化
- 多人实时协同编辑(CRDT)
- LSP / 智能补全 / Git 可视化操作面板
- 需求优先级看板 / 排期 / 甘特图
- 任务级 MR(评审走最终 merge)
- 性能测试 / 压测 / 第三方测试平台集成
- 多环境部署 / 自定义域名 / 回滚 / 蓝绿 / HTTPS
- 配额 / 限流 / 计费
- 知识条目版本管理 / 推荐
- 内嵌 MySQL/Redis 容器
- 用户级 Skills(跟随用户跨项目)
- Skills 社区市场
- 远程 MCP server(有状态/资源密集)
- Skills 版本管理

## 变更记录

| 日期 | 变更 | 原因 |
|---|---|---|
| 2026-09-21 | 初始版本 | rd-plan 启动,基于 PRD v4(已确认) + ARCH v1(已确认) + DESIGN.md(shadcn/ui New York) |
| 2026-09-21 | **全部 17 个需求点分片写完**(R1/R2/R12/R13/R17/R8/R16/R9/R10/R11/R15/R3/R4/R5/R6/R7/R14);**全部自动确认**(依据:全新项目,无既有实现;所有接口/表都是新建;复用清单完整);DEVPLAN 状态改为"已确认" | 用户指示"全部写完" |
| 2026-09-21 | **R1 修订**:email → phone(手机号);**V1 保留密码登录,短信验证码 V2 再做**;新增接口 `POST /api/auth/send-sms-code`(V2 预留);`POST /api/auth/forgot-password` / `POST /api/auth/reset-password` 改为手机号+短信验证码(V2 预留);手机号打码(前 3 位 + **** + 后 4 位);R12 邀请成员改为**手机号搜索** | 用户指示"用户使用手机号换掉 email,后续要接入短信验证码需求" |
| 2026-09-21 | **新增 R18(站内信与通知)**:站内信中心 + 钉钉 webhook(个人级 + 项目级)+ 实时 WebSocket 推送 toast;通知分级(critical/normal/info)× 通道矩阵;通知场景与接收人规则;钉钉 webhook 失效处理(连续失败 3 次标记失效);新增表 `notifications` / `user_notification_settings` + `projects` 表加 `dingtalk_webhook` / `dingtalk_enabled` 字段 | 用户确认 Q12(告警通道)后发现 PRD/DEVPLAN 无站内信模块,补充 R18 |
