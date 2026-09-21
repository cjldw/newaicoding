# 开发计划:AI Web 开发平台

> PRD:./PRD.md
> ARCH:./ARCH.md
> 创建日期:2026-09-21
> 状态:**已确认**

## 需求概述

从零搭建一个**AI 驱动的研发流程协作平台**,覆盖**需求打磨 → 开发 → 测试 → 发布 → 归档**全流程;22 个需求点(R1–R22),10 个模块(M1–M10),全部新建,无历史代码包袱。

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

### 权限与会话(按 ARCH D16/D17 决策,2026-09-21 增量)

- **双层 Guard**(D16):平台级 `require_superadmin`(R19);项目级 `require_project_role(min_level)`(**超管=虚拟 owner**,不做成员记录冗余);权限矩阵代码固化,后端为唯一事实源,前端仅隐藏入口
- **JWT 立即失效**(D17):`users.token_version` 机制——登录/禁用/改密时 +1,JWT payload 携带;每请求鉴权点查 `users(status, token_version)`,不匹配即 401(禁用即全失效,Q16);access 2h + refresh 7d 双 token 均校验
- **审计**(R19):声明式依赖 `audit(action_type)`;应用内 asyncio 队列异步写 + 重试 3 次,连续失败 critical 告警;保留 1 年,每日定时清理

### 聚合视图(按 ARCH D19 决策,2026-09-21 增量)

- R21 Dashboard / R22 四维管理:**无新表聚合查询**(SQL IN 成员项目 + 过滤);R21 口径=created_by=me,R22 口径=成员项目全量(超管=全部 active 项目);与项目内入口共用同一创建/校验 service 函数(快速创建不放宽前置校验)

### 知识库双形态(按 ARCH D18 决策,2026-09-21 增量)

- R14 知识条目(条目级)与 R20 项目知识库(文档空间级)**并存,命名隔离**
- R20 双表 `knowledge_bases` + `knowledge_docs`(树形 path);导入/同步走 D7 后台任务(bot token 拉 GitLab,事务内整体替换快照);repo_import 只读由 source_type 判定强制(角色不豁免);搜索 V1 用 MySQL FULLTEXT

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

**Runner 上的端口映射(按 D14 + D20 修订:取消本地代理层)**:
- Runner 启动容器时直接把容器端口映射到宿主机随机端口(范围 20000-29999),回报平台
- 预览:平台网关 upstream 直连 `http://{runner_host}:{mapped_port}`
- 部署:容器直接映射宿主机 `deploy_port`(10000-10099),公网直达 `http://{deploy_runner_public_ip}:{deploy_port}`
- **Runner 机器不部署 Nginx/Traefik 代理**(V2 上 HTTPS 在平台网关前置终结即可)

## 当前进度

**当前进度: 16/22 (73%) - R6 已完成并提交;下一个 R7**

| 需求点 | 名称 | 模块 | 状态 | 详情文件 |
|---|---|---|---|---|
| R1 | 用户与账号体系 | M1 | ✅ | ./DEVPLAN/R1.md |
| R2 | 项目管理(多仓库) | M1 | ✅ | ./DEVPLAN/R2.md |
| R12 | 项目成员与协作 | M1 | ✅ | ./DEVPLAN/R12.md |
| R13 | 模型接入 | M3 | ✅ | ./DEVPLAN/R13.md |
| R17 | MCP server 与 Skills 管理 | M3 | ✅ | ./DEVPLAN/R17.md |
| R8 | 任务级容器 | M5 | ✅ | ./DEVPLAN/R8.md |
| R16 | Runner 管理 | M5 | ✅ | ./DEVPLAN/R16.md |
| R9 | Web 终端 | M5 | ✅ | ./DEVPLAN/R9.md |
| R10 | 实时预览 | M5 | ✅ | ./DEVPLAN/R10.md |
| R11 | 在线编辑器 | M5 | ✅ | ./DEVPLAN/R11.md |
| R15 | 平台网关与域名 | M6 | ✅ | ./DEVPLAN/R15.md |
| R3 | 需求管理与打磨 | M4 | ✅ | ./DEVPLAN/R3.md |
| R4 | 任务(统一执行单元) | M4 | ✅ | ./DEVPLAN/R4.md |
| R5 | 开发任务 | M4 | ✅ | ./DEVPLAN/R5.md |
| R6 | 测试任务 | M4 | ✅ | ./DEVPLAN/R6.md |
| R7 | 发布任务 | M4 | ⬜ | ./DEVPLAN/R7.md |
| R14 | 归档与知识库 | M7 | ⬜ | ./DEVPLAN/R14.md |
| R20 | 项目知识库管理 | M7 | ⬜ | ./DEVPLAN/R20.md |
| R18 | 站内信与通知 | M8 | ⬜ | ./DEVPLAN/R18.md |
| R19 | 平台角色与权限体系 | M9 | ⬜ | ./DEVPLAN/R19.md |
| R21 | 全局 Dashboard | M10 | ⬜ | ./DEVPLAN/R21.md |
| R22 | 四维管理菜单 | M10 | ⬜ | ./DEVPLAN/R22.md |

(状态:⬜ 未开始 / 🔄 进行中 / ✅ 完成 / ⚠️ 有问题。这张表是**全流程唯一的续接入口**——清上下文后只读它定位,再按需读详情文件,不全量重读)

## 模块拆分与时间线

| 模块 | 包含需求点 | 依赖 | 预计耗时 | 顺序 |
|---|---|---|---|---|
| **M1 基础设施** | R1(用户/账号), R2(项目/多仓库), R12(协作/权限) | - | 5d | 1 |
| **M2 平台设置** | (R2 分片内)平台设置:GitLab 配置 / 预览·部署根域名(Q28)/ 全局参数;Runner 管理入口在 R16 | M1 | 2d | 2 |
| **M3 AI 能力** | R13(模型接入), R17(MCP server + Skills) | M1 | 3d | 3 |
| **M5 执行环境** | R8(容器), R16(Runner), R9(终端), R10(预览), R11(编辑器) | M1, M3 | 8d | 4 |
| **M6 网关与路由** | R15(网关) | M5 | 3d | 5 |
| **M4 流程引擎** | R3(需求), R4(任务), R5(开发), R6(测试), R7(发布) | M1, M3, M5, M6 | 10d | 6 |
| **M7 归档与知识库** | R14(归档/知识条目), R20(项目知识库空间) | M4(R14); R2, R11, R12, R18, R19(R20) | 6d | 7 |
| **M8 通知** | R18(站内信与通知) | M1, M4, M5 | 2d | 8 |
| **M9 平台管理与权限** | R19(角色权限/用户管理/审计日志/邀请) | M1, M2, R12, R16, R17, R18 | 4d | 9 |
| **M10 工作台与聚合视图** | R21(Dashboard), R22(四维管理) | R3, R4–R7, R12, R19 | 3d | 10 |

(依赖顺序即推荐开发顺序;无依赖的模块可并行。注:M9 的权限 Guard(`require_project_role`)建议在 M1 期先落**最小骨架**(普通角色判定),M9 再补超管虚拟 owner 与管理页,避免 M4/M5 期权限裸奔)

**总耗时**:44 天(约 9 周,1 人);多人并行可压缩到 4-5 周。

## 业务旅程(跨需求点)

| 旅程 | 链路(需求点顺序) | 关键数据传导 |
|---|---|---|
| **J1 需求全流程** | R3(需求) → R4(任务) → R5(开发) → R6(测试) → R7(发布) → R14(归档) | R3 的 PRD 被 R5/R6 消费;R6 的报告被 R7 携带;R7 的产物被 R14 归档 |
| **J2 用户接入流程** | R1(注册/绑定 GitLab token)→ R21(登录落 Dashboard)→ R12(被邀请加入项目)→ R3(创建需求) | R1 的 token 被 R12/R3/R4 使用;R1 登录跳转 R21 |
| **J3 平台初始化流程** | M2(平台设置:GitLab/Runner)→ R2(创建项目)→ R3(创建需求) | M2 的 GitLab token 被 R2 使用;Runner token 被 R16 使用 |
| **J4 文件协作流程** | R4(任务) → 文件上传 → `@文件` 引用 → AI 处理 → R11(编辑器/变更视图核查) | R4 的上传文件被 AI 消费;R11 变更视图(Q27)列出 AI 改动 |
| **J5 容器执行流程** | R4(任务) → R16(Runner 调度) → R8(容器拉起) → R9(终端) / R10(预览) / R11(编辑器) | R16 分配 Runner;R8 拉起容器(D20:端口直映射宿主机);R9/R10/R11 共用容器 |
| **J6 权限治理旅程** | R19(禁用用户)→ D17(token_version+1 → JWT 全失效)→ R4(任务取消 + 强制 push)→ R18(critical 告警) | 禁用事务联动任务取消;审计落 audit_logs(superadmin 身份);最后超管保护贯穿 |
| **J7 知识沉淀旅程** | R14(归档 → 知识条目)+ R20(文档空间:导入/同步 → 快照) | R14 条目级与 R20 文档级并存;R20 同步以仓库为准(删除源文件 → 页面移除) |
| **J8 聚合视图旅程** | R21(Dashboard 统计/最近 5 条)→ R22(四维菜单筛选/快速创建)→ R3/R4(项目内流程) | R21 口径=created_by=me,R22=成员项目全量;快速创建复用 R3/R4 校验链,前置不放宽 |

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
- 知识库空间:自动同步 / 回写仓库 / 页面版本历史 / 平台级知识库空间 / 导出 PDF / 非 .md 文件导入
- Dashboard/四维管理:实时刷新 / 自定义卡片 / 趋势图表 / 跨项目批量操作 / "指派给我的"视图 / 自定义列
- 内嵌 MySQL/Redis 容器
- 用户级 Skills(跟随用户跨项目)
- Skills 社区市场
- 远程 MCP server(有状态/资源密集)
- Skills 版本管理
- (R19)平台角色细分(仅 superadmin/user)/ 权限点动态配置 / 组织层级 / 超管操作审批流

## 变更记录

| 日期 | 变更 | 原因 |
|---|---|---|
| 2026-09-21 | 初始版本 | rd-plan 启动,基于 PRD v4(已确认) + ARCH v1(已确认) + DESIGN.md(shadcn/ui New York) |
| 2026-09-21 | **全部 17 个需求点分片写完**(R1/R2/R12/R13/R17/R8/R16/R9/R10/R11/R15/R3/R4/R5/R6/R7/R14);**全部自动确认**(依据:全新项目,无既有实现;所有接口/表都是新建;复用清单完整);DEVPLAN 状态改为"已确认" | 用户指示"全部写完" |
| 2026-09-21 | **R1 修订**:email → phone(手机号);**V1 保留密码登录,短信验证码 V2 再做**;新增接口 `POST /api/auth/send-sms-code`(V2 预留);`POST /api/auth/forgot-password` / `POST /api/auth/reset-password` 改为手机号+短信验证码(V2 预留);手机号打码(前 3 位 + **** + 后 4 位);R12 邀请成员改为**手机号搜索** | 用户指示"用户使用手机号换掉 email,后续要接入短信验证码需求" |
| 2026-09-21 | **新增 R18(站内信与通知)**:站内信中心 + 钉钉 webhook(个人级 + 项目级)+ 实时 WebSocket 推送 toast;通知分级(critical/normal/info)× 通道矩阵;通知场景与接收人规则;钉钉 webhook 失效处理(连续失败 3 次标记失效);新增表 `notifications` / `user_notification_settings` + `projects` 表加 `dingtalk_webhook` / `dingtalk_enabled` 字段 | 用户确认 Q12(告警通道)后发现 PRD/DEVPLAN 无站内信模块,补充 R18 |
| 2026-09-21 | **PRD 增量对齐(R19–R22 + Q25/Q26/Q27),完成全部 PLAN 计划**:① **新增 4 个分片** R19(平台角色与权限:双层 Guard D16 / token_version D17 / audit_logs + invitations 表 / 用户管理与审计页)、R20(项目知识库:双表 + 后台导入 + repo_import 只读)、R21(Dashboard:四卡片 + 最近 5 条,created_by=me)、R22(四维管理菜单:聚合列表 + 快速创建复用校验链);② **Q25/D20 修订**:取消 Runner 本地代理——R8/R10/R15/R16 分片及本文件 Runner 章节改为网关直连 `runner_host:mapped_port`;③ **Q26 修订**:文档目录统一 `docs/{YYYYMMDD}_{descSlug}_{taskShortId}/`(归档 `_archive`)——R3/R5/R6/R7/R14 分片路径全部更新;④ **Q27 修订**:文件树「全部/变更」双视图——R11 补变更清单接口 `GET /api/tasks/{id}/files/changes` 与双视图交互,R5 补消费方验收;⑤ **R1 联动**:登录跳转改 `/`(Dashboard),users 表补 role/token_version;⑥ **R12 联动**:邀请改手机号精确搜索、12001 文案改"联系管理员邀请注册"、鉴权补"owner 或超管"、矩阵补超管行;⑦ 技术约定补 D16–D19 小节;模块表新增 M9/M10(R20 并入 M7);业务旅程更新 J2、新增 J6/J7/J8;总耗时 34d → 44d;**R19–R22 自动确认**(依据:全新功能无既有实现;接口/表与 ARCH 接口概要、数据模型概要一一对齐;复用清单已核对存在) | 用户指示"完成所有的PLAN计划";PRD 2026-09-21 增量(新增 R19–R22,Q25–Q27)尚未同步到 DEVPLAN |
| 2026-09-21 | **增量2:品牌定名「旗程」(仅中文名,用户否决英文标识 FLAGWAY)+ 域名策略 Q28/Q29(PRD 已确认)**:① 视觉原型 `vp/index.html` 品牌更名(标题/favicon/侧栏/登录页),Logo 为"三段升旗"(打磨→开发→发布,纯 SVG,rd-dev 可直接复用 `LOGO` 常量);② **Q28**:预览/部署根域名(`preview_base_domain` / `deploy_base_domain`)入平台设置——R2 分片补实 `platform_settings` 单例表 + `GET/PUT /api/admin/platform-settings` 契约(M2 不再隐含);③ **Q29**:R7 发布任务新增 `deploy_host` 字段(默认 `{slug}.{deploy_base_domain}` 预填可改,合法主机名 + 全平台唯一,错误码 7003;仅 HTTP,DNS 自行解析不阻塞创建),R15 按 Host 精确匹配路由;④ 联动:R10 预览 host 改 `{preview_base_domain}` 拼接、R19 权限矩阵与审计枚举补 `platform_settings.update`、PRD R7/R15/概念模型/范围外同步修订 | 用户拍板:"1. 叫旗程;2. 域名在发布时候可以设置";随后补充:"不要 FLAGWAY 这个标识" |
| 2026-09-21 | R1 启动,开发环境基线确认:① 中间件——MySQL(120.27.217.194:3306/aicoding,charset utf8mb4)与 Redis(121.43.42.203:6379)写入后端 `.env`(不入库,仓库只留 `.env.example` 占位);**Redis R1 仅做配置占位,不建任何功能**(计划中无 Redis 依赖,留作后续缓存/会话扩展);② **文件上传策略**:上传文件落容器目录、任务结束随容器丢弃,平台不存副本(R4 落地依据);③ **UI 实施轨**:所有前端需求点以视觉原型 `vp/index.html` 为轨1样板页(布局/交互/文案对照原型;色值字号仍以 DEVPLAN 设计规范 token 为准);④ 组件策略:shadcn 风格组件手写(Button/Input/Card 等无 Radix 依赖的),避免 CLI 脚手架依赖,需要 Radix 的组件在对应需求点引入 | 用户提供基础中间件信息与 UI 实现要求 |
| 2026-09-21 | **R1 完成闭环**:后端(20 文件:models/schemas/api/services/core + alembic 两笔迁移,users 表含 role/token_version/login_fail_count/locked_until;编译零错误;冒烟 /health /docs /openapi.json 9 路径)→ QA 套件 64 用例经三轮红绿迭代全绿(修复:登录锁定 1006+remaining_seconds、GitLab mock 注入机制、scope 1013 AND 校验、锁定字段迁移)→ 前端(Vite+React18+TS+Tailwind3.4 token 照抄,7 路由独立页面 + SettingsLayout,build 零错误,ui-check 66/67✅ + 1 项 V2 占位)→ 审计通过(无阻塞项)。**决策留痕**:① 本机 Python 3.10(规格 3.12,代码兼容;pyproject requires >=3.10);② FastAPI 0.104 + Pydantic 2.5.3 的 OpenAPI enum_schema 缺失用 main.py 兼容补丁(pip 网络受限无法升级);③ bcrypt 锁定 4.x(passlib 1.7.4 与 5.x 不兼容);④ 登录锁定用 DB 字段(login_fail_count/locked_until)而非 Redis;⑤ GitLab mock 注入:gitlab_service 模块级 _test_transport + conftest autouse patch MockTransport.__enter__/__exit__;⑥ 收口审计采用审计 subagent 覆盖核查(code-review skill 需 git 基线,绿地无基线;rd-check 阶段做全量兜底);⑦ DEPLOY.md 记录 users DDL 全文与环境变量(真实密钥只在 backend/.env,不入库) | 多角色 tdd 闭环(QA/API Tester + Backend Architect + Frontend Developer + Code Reviewer) |
| 2026-09-21 | **R1/R2 待提交工作落地**:计划文档增量与 R1 实现分两笔提交(d7fd2a3 / a452549);.gitignore 补会话产物(.playwright-mcp/.scratch/dash.png) | 用户授权"按建议确认"后进入连续模式 |
| 2026-09-21 | **R2 完成闭环 + subagent 基础设施降级决策**:① **subagent 8 派 7 死**(QA/后端/前端/审计均反复 autocompact 超限,重派加纪律仍死),后端与收口审计降级为**主 agent 直接实现/直审**,多角色意图部分保留(QA 红测文件由首轮 QA agent 产出、前端由第三次重派的 frontend agent 完成,ui-check 46/46);依赖 rd-check 全量审查兜底;② 后端:三表(models/project.py 修正前序 agent 遗留的 (project_id,role) 全列唯一错误约束 → main 唯一改服务层保证 + 组合唯一硬保证同 repo 重复)+ alembic a7d21c9e5f40 + 8 项目接口 + 3 平台设置接口(敏感项 AES-GCM/打码/白名单/2007/19002,test-connection 为分片"测试连接"按钮的自定契约 POST /api/admin/platform-settings/test-connection)+ require_superadmin 最小 Guard;③ 测试 110 全绿(64 存量 + 46 新增)。**修复记录**:QA 红测缺陷(假 project_id 断言成功→直插 DB 造数据;GitLab 用例补 _seed_gitlab_settings);R1 bootstrap"首个用户=superadmin"致非超管用例失效→conftest 增 second_user_headers;conftest 清理扩至 4 表(platform_settings 残留会污染 2001 场景);PATCH 后 onupdate 字段 MissingGreenlet→显式 await db.refresh;projects 表补 deleted_at(行为规格要求,模型节遗漏);④ 前端:api/projects.ts + 4 项目页面(route-as-modal 创建对话框 max-w-lg)+ 平台设置页 + MainLayout 侧栏(项目/超管平台设置入口),ui-check 46/46(审计发现报告 #28-34 期望项标签笔误,实现代码正确,已修正留注);⑤ DEPLOY.md 记录三表 DDL + 上线配置动作 | 用户指示"完成剩下的所有任务,都按你建议来确认";连续模式第 2 点(R2) |
| 2026-09-22 | **R12 完成闭环**:后端主 agent 实现(project_members 表 + alembic c2e8b4d7a910 + 5 成员接口 + GET /api/users/search 手机号精确搜索 + **require_project_role 项目级 Guard 正式落地**:viewer(1)<editor(2)<owner(3),超管=虚拟 owner 不落成员行 D16;R2 权限升级:查看=成员、追加绑定仓库=editor+、其余 owner)+ GitLab 成员同步(add/remove/update,owner40/editor30/viewer20,非关键路径容错)+ 前端 subagent 成员管理 Tab(300ms 防抖搜索/三对话框/转让入口,build 通过 ui-check 全对齐)。**测试 128 全绿**(新增 18 条)。**决策留痕**:① owner 成员行懒回填(R2 建项目早于本表);② viewer 邀请同步 GitLab 用 Reporter(20) 非分片字面 Developer(30)——与改角色节映射一致,避免只读角色获写权限;③ 超管转让后无成员行(虚拟 owner 语义),转让用例须用普通用户;④ search 不足 11 位返回 null 防前缀枚举。subagent 策略稳定为:**前端派发(纪律模板存活率 2/2)+ 后端/QA/审计主 agent 直做** | 连续模式第 3 点(R12) |
