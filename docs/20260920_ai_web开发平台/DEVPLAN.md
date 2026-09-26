# 开发计划:AI Web 开发平台

> PRD:./PRD.md
> ARCH:./ARCH.md
> 创建日期:2026-09-21
> 状态:**已确认**(增量3/增量4 收口见各行;**增量5(R31)已确认**,2026-09-24,A1–E1 用户确认;待确认清单空)

## 需求概述

从零搭建一个**AI 驱动的研发流程协作平台**,覆盖**需求打磨 → 开发 → 测试 → 发布 → 归档**全流程;31 个需求点(R1–R31),10 个模块(M1–M10),全部新建,无历史代码包袱。

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

**当前进度: 增量3(R23–R27):5/5 (100%) - R27 判据 5 真机复现通过(2026-09-25),增量3 收官 | 增量4(R28–R30):3/3 (100%) - 全部完成,引导进入 /rd-check | 增量5(R31):1/1 (100%) - 完成,待提交与 /rd-check | rd-fix 第 27 轮收敛:BUG-UI-071/072/073 verified 迁移 ISSUES.md;BUG-034 待用户启 LLM 代理(0.0.0.0:18765)后回归 | rd-fix 第 28 轮收敛:R21.F1(BUG-051 工作台门槛)verified 迁移 ISSUES.md——统计数字对账无误,口径变更诉求归 /rd-plan**

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
| R7 | 发布任务 | M4 | ✅ | ./DEVPLAN/R7.md |
| R14 | 归档与知识库 | M7 | ✅ | ./DEVPLAN/R14.md |
| R20 | 项目知识库管理 | M7 | ✅ | ./DEVPLAN/R20.md |
| R18 | 站内信与通知 | M8 | ✅ | ./DEVPLAN/R18.md |
| R19 | 平台角色与权限体系 | M9 | ✅ | ./DEVPLAN/R19.md |
| R21 | 全局 Dashboard | M10 | ✅ | ./DEVPLAN/R21.md |
| R22 | 四维管理菜单 | M10 | ✅ | ./DEVPLAN/R22.md |
| R16.F1 | 修复 BUG-007:Runner 镜像缺 R9/R11 文件 | M5 | ✅(fixed,构建冒烟待部署机) | ./DEVPLAN/R16.F1.md |
| R19.F1 | 修复 BUG-001 超管角色字段传递与前端恢复 | M9 | ✅ | ./DEVPLAN/R19.F1.md |
| R19.F2 | 修复 BUG-002/003/004 超管管理块前端补全(用户管理/审计日志页+守卫+外壳) | M9 | ✅ | ./DEVPLAN/R19.F2.md |
| R1.F1 | 修复 BUG-005 测试套件与 dev 库隔离 | M1 | ✅ | ./DEVPLAN/R1.F1.md |
| R5.F1 | 修复 BUG-032/033 对话链路 Runner 连接稳定性(runner send 锁+to_thread 解堵/平台快速失败+校验前移+TimeoutError 归一化) | M4/M5 | ✅(fixed;E2E 全判据过,AI 回复待 BUG-034 环境) | ./DEVPLAN/R5.F1.md |
| R19.F2+ | 修复 BUG-006 管理页两处规格细节(空态文案/唯一超管禁用按钮) | M9 | ✅ | ./DEVPLAN/R19.F2.md(补遗) |
| R2.F1 | 修复 BUG-008/009 gitlab_bot_group_id 类型宽容(前轮已实施,本轮回归确认) | M2 | ✅(BUG-009 verified 待用户真实 GitLab 复验) | ./DEVPLAN/R2.F1.md |
| R19.F3 | 修复 BUG-UI-001 面包屑统一两级且父级可点击 | M9 | ✅(verified,迁移 ISSUES.md) | ./DEVPLAN/R19.F3.md |
| R16.F2 | 修复 BUG-UI-003 Runner 表格补 .card 包裹 | M5 | ✅(verified,迁移 ISSUES.md) | ./DEVPLAN/R16.F2.md |
| R2.F2 | 增强 BUG-UI-004 内容区页头统一 icon+标题+换行+说明(12 页;初版误改侧栏已回滚) | M1 | ✅(verified,迁移 ISSUES.md) | ./DEVPLAN/R2.F2.md |
| R2.F3 | 守卫 BUG-UI-005 项目页保留右上角新建按钮 + 删空态重复按钮 | M1 | ✅(verified,迁移 ISSUES.md) | ./DEVPLAN/R2.F3.md |
| R19.F4 | 修复 BUG-UI-006 用户管理筛选栏与表格零间距(归位 .fbar) | M9 | ✅(verified,迁移 ISSUES.md) | ./DEVPLAN/R19.F4.md |
| R2.F4 | 修复 BUG-010 测试连接结果误标成功(GitLab 401 透传被渲染为成功样式) | M2 | ✅(verified,迁移 ISSUES.md) | ./DEVPLAN/R2.F4.md |
| R2.F5 | 修复 BUG-012 GitLab PAT 鉴权头用错(Bearer → PRIVATE-TOKEN;BUG-009 真根因) | M2 | ✅(verified:端到端 ok=true v11.7.0,迁移 ISSUES.md) | ./DEVPLAN/R2.F5.md |
| R2.F6 | 修复 BUG-013 私有组建 internal 仓库被拒(建仓可见性按组自动降级) | M2 | ✅(verified:冒烟建仓+clone+push 全通,迁移 ISSUES.md) | ./DEVPLAN/R2.F6.md |
| R2.F7 | 修复 BUG-UI-063 详情页面包屑补全上级链 | M1 | ✅(fixed;9 页静态断言+tsc/build 过,verified 待浏览器) | ./DEVPLAN/R2.F7.md |
| R8.F1 | 修复 BUG-026 devbox 基础镜像重建(universal 退役→devcontainers/typescript-node) | M5 | ✅(verified 2026-09-23,详情文件为准;表格 🔄 系陈旧) | ./DEVPLAN/R8.F1.md |
| R8.F2 | 修复 BUG-027 Runner 事件监听归属过滤 + 心跳饿死(events 线程泵送 + qicheng.managed 标签过滤) | M5 | ✅(fixed:心跳 30s 刷新实测 + 越权接管 0,verified 待长观察) | ./DEVPLAN/R8.F2.md |
| R8.F3 | 修复 BUG-029 容器内 git clone 认证缺失(GITLAB_TOKEN oauth2 重试 + remote 洗净) | M5 | ✅(fixed+verified:E2E round3/4) | ./DEVPLAN/R8.F3.md |
| R4.F1 | 增强 BUG-UI-064 任务工作台三面板全屏/保存/滚动(Terminal/AI 对话/编辑器) | M4 | ✅(fixed;tsc+build 过,verified 待浏览器) | ./DEVPLAN/R4.F1.md |
| R4.F2 | 修复 BUG-UI-065 工作台缺陷批(WS 代理/终端关 tab/Diff 直显/对话反馈)+ 四项 UI 增强(状态栏/三处拖拽/任务头 chips) | M4 | ✅(fixed;tsc+build 过,verified 待浏览器;vite dev 需重启) | ./DEVPLAN/R4.F2.md |
| R4.F3 | 对齐 BUG-UI-066 任务工作台 vp #/t/T-301 版式(wb-head/三栏 grid/右栏 对话·终端·活动 Tab 组) | M4 | ✅(首修被用户打回,**已被 R4.F4 照抄重写取代并验收通过**——非待办,状态卫生修正) | ./DEVPLAN/R4.F3.md |
| R4.F4 | 二修 BUG-UI-066 任务工作台照抄重写 vp #/t/T-301(全出血骨架/wb-head/五类型中栏/右栏三 Tab/CSS 原值/并排视觉硬门禁) | M4 | ✅(fixed;并排视觉核对+功能扫测过,tsc+build 零错;待用户验收) | ./DEVPLAN/R4.F4.md |
| R17.F1 | 修复 BUG-011 MCP/Skills 入口断链(设置按钮接线 + 侧栏补 Skills 市场) | M3 | ✅(verified:浏览器实测侧栏入口+页面渲染通过) | ./DEVPLAN/R17.F1.md |
| R22.F1 | 修复 BUG-014 四维管理页 key 字段契约缺失崩溃 | M10 | ✅(verified:浏览器四维页实测不崩,迁移 ISSUES.md) | ./DEVPLAN/R22.F1.md |
| R23 | 平台默认 LLM 配置与项目回退链(增量3) | M3 | ✅ | ./DEVPLAN/R23.md |
| R24 | 平台设置页布局改版(增量3) | M2 | ✅(fixed;判据 1-7 Playwright 实证,tsc+build 零错,待用户验收) | ./DEVPLAN/R24.md |
| R25 | 审计日志全量接入(增量3) | M9 | ✅(fixed;43/44 接入+1 无宿主登记;新增 pytest 19 例全绿,全量 293+1s 零回退,待用户验收) | ./DEVPLAN/R25.md |
| R26 | Runner 管理终端(增量3) | M5 | ✅(fixed;pytest 10 例全绿,全量 303+1s;6003 全链浏览器实证;判据 4/8/11 真实 pty 场景待 rd-test) | ./DEVPLAN/R26.md |
| R27 | manual 绑定修复与错误细分(增量3) | M1 | ✅(判据 5 真机复现通过 2026-09-25:token 重录生效,A 成功/B 2011/C 2013 逐字一致,零残留;六判据全 ✅,增量3 收官) | ./DEVPLAN/R27.md |
| R9.F1 | 增强 BUG-037 任务页终端自动进入 claude 与对话同一会话(任务级 claude_session_id 持久化 + --session-id/--resume 接线 + 终端 exec 自动进 claude) | M5(波及 M4) | ✅(fixed;单测 9 新增+回归过,R9.F1 触碰面零失败;verified 待真实容器浏览器实测) | ./DEVPLAN/R9.F1.md |
| R2.F9 | 修复 BUG-038 平台设置单键解密失败打挂整页(_decode_stored 逐键容错折叠 None;2001/13005 干净降级;0 前端) | M2(波及 M3 回退链) | ✅(verified:红测 9 failed→11/11 绿,全量 333/1s/0;真实环境重启后 GET 200 + 3 失效键未配置降级,迁移 ISSUES.md;5 条存量密文重录归用户运维) | ./DEVPLAN/R2.F9.md |
| R19.F5 | 修复 BUG-039 审计日志页时间筛选发 UTC 串把全表滤空(接口返回空;本地裸串适配 + isError + start>end 禁查询) | M9(0 后端) | ✅(verified:Red 0 条→Green 69 条,NY 时区判据 PASS,时区钉死 GMT+8(前端 formatGmt8 + 后端 time_zone='+08:00' 固化);tsc/build/pytest 398/1s/0;迁移 ISSUES.md) | ./DEVPLAN/R19.F5.md |
| R28 | 用户信息修改增强(昵称、头像本地上传)(增量4) | M1 | ✅ | ./DEVPLAN/R28.md |
| R29 | 平台导览(左下角入口)(增量4) | M10 | ✅(fixed;tsc/build 零错,判据 1-10 Playwright 实测全过,审计 0 阻塞,待用户验收) | ./DEVPLAN/R29.md |
| R30 | 黑白主题切换(增量4) | M10 | ✅(fixed;tsc/build 零错,判据 1-11 Playwright 实测全过;顺带修复主按钮白底白字存量缺陷;待用户验收) | ./DEVPLAN/R30.md |
| R31 | Runner 本地快速创建与本机生命周期管理(增量5) | M5 | ✅(fixed;pytest 28+1s/runner 34/回归 58 零回退;真机 E2E 判据 1/4/5/6 过;待用户验收) | ./DEVPLAN/R31.md |
| R2.F10 | 修复 BUG-049 项目卡片需求数/成员数为硬编码演示数据 | - | ✅(verified;真机 API 三项目逐项与 DB 一致;已迁移 ISSUES.md) | ./DEVPLAN/R2.F10.md |
| R28.F1 | 修复 BUG-040 个人设置入口断链(用户下拉补「个人设置」,头像编辑/GitLab Token/通知设置可达) | M1 | ✅(fixed;判据 1-5 Playwright 实测全过,tsc/build 零错;verified 待用户浏览器复验) | ./DEVPLAN/R28.F1.md |
| R26.F1 | 修复 BUG-041 Runner 终端 6003 对非容器化 runner 误报"版本过旧"(细分文案:键缺失=版本过旧/空串=非容器化,码不动 0 前端) | M5 | ✅(verified 迁移 ISSUES.md;pytest 11/11 + 真机接口复验新文案,后端已重启) | ./DEVPLAN/R26.F1.md |
| R16.F3 | 修复 BUG-042 删除 Runner 被孤儿容器行卡死(16001 收窄为容器关联任务 running;非进行中放行) | M5 | ✅(verified 迁移 ISSUES.md;第 21 轮真机删除实证:local-win-test 行消失+旧 token register_failed) | ./DEVPLAN/R16.F3.md |
| R16.F4 | 修复 BUG-045 机器信息增强(Windows 内存采集 ctypes 修复 + os_version/hostname/ip/disk/cpu_model 字段扩充;前端 formatMachine 两行展示;后端零改动) | M5 | ✅(verified 迁移 ISSUES.md;runner pytest 4 新增+全量 31/31、tsc 0 错、真机重启后 DB 全字段落库 mem 31.8GB) | ./DEVPLAN/R16.F4.md |
| R9.F2 | 修复 BUG-046 新建终端 xterm RenderService 崩溃(safeFit 统一守卫:双 rAF/尺寸>0/disposed/try-catch)+ BUG-UI-070 终端滚动条美化(.xterm-viewport 细条双主题) | M5(波及 R26 Runner 终端) | ✅(原崩溃真机实证消失;StrictMode 伪影根除;070 verified 迁移;浏览器零错终验归用户一瞥——两会话超管互踢致驻留不稳) | ./DEVPLAN/R9.F2.md |
| R26.F2 | 修复 BUG-047 Runner 终端 6002 提供强制关闭并新建(POST ?force=true 复用关闭链路清活跃会话后放行;前端 6002 分支渲染强制按钮) | M5 | ✅(fixed;test_r26_runner_shell 12/12 含新 Red→Green 用例;真机 API 三步链+runner 日志+DB 全实证;tsc 0 错) | ./DEVPLAN/R26.F2.md |
| R31.F2 | 修复 BUG-048 宿主终端 WS 零输出(cmd.exe 缺 /K 管道下非交互即退 + 裸 \r 行尾仿真缺失;runner 侧双层修复,容器 pty 零改动) | M5(R31.F1 数据面) | ✅(verified 迁移 ISSUES.md;runner 35/35 含存活回归门;真机 WS 全双工 PASS——含 xterm 裸 \r 路径) | ./DEVPLAN/R31.F2.md |
| R31.F3 | 修复 BUG-049 需求修正:本机快速创建改 Docker 容器形态(镜像自动构建+BASE_IMAGE 自适应回退+exec cwd=/app 适配;子进程形态废弃不再新启) | M5(R31 核心机制) | ✅(verified 迁移 ISSUES.md;后端 51/51;真机:首建 145s 自动构建→容器 online→self_container_id=容器 id→终端真 pty 回路 PASS) | ./DEVPLAN/R31.F3.md |
| R26.F3 | 修复 BUG-050 终端读循环 SocketIO 兼容(硬编码 .recv 对标准 Linux docker 的 SocketIO 秒崩;探测式 read 兜底) | M5(runner terminal_manager;波及全部 Linux 容器形态) | ✅(verified 迁移 ISSUES.md;runner 36/36 含新增回归;真机容器终端回路 PASS) | ./DEVPLAN/R26.F3.md |
| R31.F1 | 修复 BUG-043 本机/非容器 Runner 无终端(宿主 shell 降级通道:runner subprocess cmd/bash + __host__ 哨兵,超管+审计) | M5 | ✅(verified 迁移 ISSUES.md;runner 6/6 + 后端 11/11 + 真机 code=0;浏览器交互归 rd-test) | ./DEVPLAN/R31.F1.md |
| R14.F1 | 修复 BUG-UI-071 归档接口全量 500(stray import 一行修复)+ useTourSteps 导览链式请求改开启才发 | M7(波及 R29/M10) | ✅(verified 迁移 ISSUES.md;Red→Green 2/2+触碰面 21/21 两轮;真机 archive 200/404 主会话独立复放一致;tsc/build 0 错) | ./DEVPLAN/R14.F1.md |
| R28.F2 | 修复 BUG-UI-072 超管头像文件 404(失效引用清库 + 前端失败 URL 记忆不重复请求) | M1 | ✅(verified 迁移 ISSUES.md;两列引用置 NULL 读回断言;前端 failedAvatarUrls 三消费点;tsc/build 0 错) | ./DEVPLAN/R28.F2.md |
| R19.F6 | 修复 BUG-UI-073 审计日志「详情」列断词换行(列 nowrap;0 后端) | M9 | ✅(verified 迁移 ISSUES.md;nowrap+col 110 断言落位;tsc/build 0 错;视觉归走查) | ./DEVPLAN/R19.F6.md |
| R21.F1 | 修复 BUG-051 工作台门槛口径错位(summary 增 visible_projects,前端门槛与数据同源;非 owner 成员不再被空态顶掉) | M10 | ✅(verified 迁移 ISSUES.md;Red→Green+test_dashboard 10/10;真机 visible_projects=1 主会话独立复放一致;tsc/build 0 错) | ./DEVPLAN/R21.F1.md |

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
| **增量3(2026-09-23)** | R23(平台默认 LLM,M3)/ R24(平台设置页布局,M2)/ R25(审计全量接入,M9)/ R26(Runner 终端,M5)/ R27(manual 绑定修复,M1) | 复用 R13/R19/R16/R9/R2 既有设施,无新表 | 3d | 11(可并行:R25 ∥ R23+R24 ∥ R26 ∥ R27) |
| **增量4(2026-09-23)** | R28(用户信息修改增强,M1)/ R29(平台导览,M10)/ R30(黑白主题切换,M10) | R28 依赖 R1;R29 依赖 R1/R21/R22;R30 无依赖 | 2d | 12(可并行:R30 ∥ R28 → R29) |
| **增量5(2026-09-24)** | R31(Runner 本地快速创建与生命周期,M5) | 复用 R16 WS 协议/R4 stop 链/R19 守卫/R25 审计;runners 表加 1 列 | 1.5d | 13(R31;runner/main.py 协议分支同批) |

(依赖顺序即推荐开发顺序;无依赖的模块可并行。注:M9 的权限 Guard(`require_project_role`)建议在 M1 期先落**最小骨架**(普通角色判定),M9 再补超管虚拟 owner 与管理页,避免 M4/M5 期权限裸奔)

**总耗时**:46 天(约 9.5 周,1 人);多人并行可压缩到 4-5 周。

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
| **J9 LLM 回退链旅程(增量3)** | R23(平台默认配置)→ R13(resolve_config 回退)→ R4/R8(任务创建 env/SDK 注入生效配置) | platform_settings.llm_* 被 resolve_config 消费;项目配置存在时平台默认不参与;resolvable 端点驱动前端入口禁用与提示 |
| **J10 审计旅程(增量3)** | R25(44 挂点全量写入)→ R19(审计查询页按时间/用户/类型过滤) | 各模块操作产生 action_type 记录;登录失败/破坏性命令等安全事件可追溯;写失败不阻塞业务 |
| **J11 Runner 排障旅程(增量3)** | R26(超管开 Runner 终端)→ R25(terminal.destructive_command / runner.terminal_open 审计) | Runner 自报 self_container_id;复用 exec 协议;会话即开即毁 |
| **J12 用户个性化旅程(增量4)** | R28(上传头像)→ R1(getMe 返回 avatar_url)→ 全局布局显示头像 | avatar_url 被 MainLayout/ProfileSettings 消费;移除头像后回退首字母 |

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
- (增量3 R23)平台默认 LLM 主/备多组 / 项目级"禁用回退"开关
- (增量3 R24)平台管理一级导航重构 / 设置项搜索
- (增量3 R25)审计日志导出 / 业务失败操作记录(除登录失败)
- (增量3 R26)进入任务容器 exec 终端(工作台已覆盖)/ 多 Tab 会话 / 会话恢复 / 录制回放 / 文件上传到 Runner
- (增量4 R28)头像裁剪(V1 仅预览)
- (增量4 R29)交互式分步导览(driver.js 高亮元素,V1 做静态链接列表)
- (增量4 R30)多主题/自定义配色(V1 仅亮/暗两套)

## 待确认清单(增量3,2026-09-23)——已清零

> 以下 3 项负向规格与 Q-D(端点不存在口径)已于 2026-09-23 全部确认(用户"ok"),**待确认清单清零**;R23/R25/R27 自动确认依据见变更记录。

- [x] R25:登录失败 detail 记录手机号——**确认:记,脱敏前 3 + **** + 后 4**(同 R1 规范)
- [x] R26:同一 Runner 并发终端会话上限——**确认:1**(第二个打开返回 6002"该 Runner 已有终端会话,请先关闭")
- [x] R26:打开 Runner 终端会话记审计——**确认:记 `runner.terminal_open`**(高敏操作)
- [x] Q-D(R25):登出/Runner 启用/销毁前强制 push 三事件无实现宿主——**确认:不接 + ISSUES.md 登记口径**(强制 push 随 R8 后续实现补接)

## 待确认清单(增量4,2026-09-23)——已清零

> 以下 3 项技术细节已于 2026-09-24 按当前推荐方案确认(用户直接进入 /rd-dev,自主模式采纳推荐值并留痕,见变更记录):

- [x] **Q41** R28 头像上传存储路径——**确认:后端本地磁盘 `./data/avatars/{user_id}/`,文件走 `GET /api/files/avatars/{filename}` 公开访问**(R28 已按此实施,留痕确认)
- [x] **Q42** R29 导览步骤动态生成——**确认:复用现有接口,前端并行请求维度取第一条,有数据显示步骤**(与分片接口契约一致)
- [x] **Q43** R30 暗色主题参考风格——**确认:GitHub Dark 风格(#0d1117/#161b22/#21262d);语义色徽章不随主题变**(R30 开发时执行)

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
| 2026-09-22 | **UI 对齐迭代(用户反馈:UI 与 vp 原型有差距)**:① vp 原型设计系统整体移植进 globals.css @layer components(shell/sidebar/topbar/card 系列/bdg 三件套/tbl/tabs/tl 时间线/term/toast/pcard/act/kv/empty/login),值全部走语义 token(--blue-bg 三件套/--term-*/--vp-radius);② MainLayout 重构为 vp 应用外壳(220px 侧边栏:logo-mark 深色方块 30px+白旗 SVG/分组导航[顶部/项目管理四维/知识/平台管理·仅超管]/tour 用户框;main+topbar[铃铛/用户/退出]);③ index.html 补 Geist 字体 preconnect+stylesheet(此前 Geist 根本未加载——字体风格差距的直接原因)+ 标题改"旗程 · AI 研发流程平台";④ base 排版对齐原型 14px/1.55;⑤ tailwind.config 扩展语义色映射(blue/green/amber/red/violet/zinc/term 的 bg-fg-border 三件套)——页面可用标准 Tailwind 工具类;⑥ Dashboard 对齐原型(dcard 四卡片/grid2 最近 5 条/空态引导);⑦ 三个并行 agent 完成:登录页+项目列表(pcards)/四维管理页(/manage/* 四页)/管理后台 5 页对齐;踩坑:块注释内含 `*/` 序列导致注释早闭(postcss "Unexpected '/'")、JSON 列原地改不触发 UPDATE、FULLTEXT 仅索引已提交行(测试需显式 commit) | 用户反馈 UI 与原型差距;严格按 Tailwind 规范 + DESIGN.md 风格 |
| 2026-09-22 | **新增 R16.F1 修复 BUG-007**:docker/runner/Dockerfile 仅 COPY main.py + container_manager.py,缺 R9 的 terminal_manager.py 与 R11 的 file_watcher.py,Runner 镜像启动即 ModuleNotFoundError | rd-ship 发布检查单 §0 阻塞项(rd-ship 只记录不修码,转 rd-fix 循环) |
| 2026-09-22 | **新增 R2.F1 修复 BUG-008/009**:gitlab_bot_group_id 前端传 string 后端 isinstance(int) 严格拒绝 → 平台设置存不了 → bot 配置不完整 → 建仓拉码 403(连带) | 用户实测(平台设置保存报"要整形"、GitLab 拉码无权限) |
| 2026-09-22 | **rd-fix 新增修复点 R19.F1 / R19.F2**:用户报告"superadmin 看不到平台设置等超管信息"→ 建 BUGS.md 登记 BUG-001(用户报告)+ BUG-002/003/004(rd-fix 分析发现的 R19 前端批次遗漏:用户管理/审计日志页未实现、admin 路由无角色守卫、admin 路由游离外壳外)。BUG-001 根因=后端 LoginUserInfo/UserProfileResponse schema 丢 role 字段 + 前端 authStore user 不持久化且 init 不调 getMe(详见 .scratch/fix-analysis.md);BUG-002~004 属实现遗漏非规格缺口(R19 分片有完整页面/守卫规格),不回 rd-plan。AdminNav.tsx 未单独建文件记为已接受偏差 | 测试发现(rd-fix 修复循环) |
| 2026-09-22 | **⚠️ 数据事故与修复点追加 R1.F1 / R19.F2 补遗**:① R19.F1 修复执行中跑全量 pytest 触发**既有的测试基建缺陷**——`tests/conftest.py` 直连 dev 库 aicoding 且每轮清理 18 张表,导致 users/projects/audit_logs 等被清空(BUG-005);已通过正式注册接口恢复 18767169856(superadmin,bootstrap 首个用户)/ 13800005678(user),密码统一重置为临时值 Qicheng@2026,**platform_settings 如有历史配置需重新配置**;② 新增 R1.F1:conftest 覆盖 DATABASE_URL 指向隔离库 aicoding_test(已创建)+ 非测试库拒绝执行护栏;③ 回归又发现 BUG-006(审计空态文案不符、唯一超管禁用按钮未置灰),并入 R19.F2 补遗 | rd-fix 回归阶段(数据事故透明留痕) |
| 2026-09-22 | **rd-fix 循环收敛:BUG-001~006 全部 verified,迁移 ISSUES.md**。修复点 R19.F1(role 字段传递 + 前端 hydrate)/ R19.F2(用户管理/审计日志页 + RequireRole 守卫 + admin 路由入外壳)/ R19.F2 补遗(空态文案 + 唯一超管禁用按钮置灰)/ R1.F1(conftest 隔离到 aicoding_test + 护栏 + fallback 补建 2 个 ngram FULLTEXT 索引)。回归:后端 256/256 全绿(判据 A:跑后 dev 库 users 仍 2 行;判据 B:故障注入被护栏拦截)、前端 build 零错误、Playwright 双角色端到端实证(超管四入口/刷新持久/普通用户无入口且直达重定向)。修复报告在 `.scratch/R19.F1/ R19.F2/ R1.F1/`,分析在 `.scratch/fix-analysis.md`。**未提交,待用户确认** | rd-fix 第 2 轮收敛 |
| 2026-09-22 | **rd-fix 第 3 轮(用户 UI 反馈)新增修复点 R19.F3 / R16.F2 / R2.F2 / R2.F3 / R19.F4**:① 面包屑统一(用户拍板推翻 BUG-UI-001"不修":父级一律可点击 `<a>` + Runner 管理补两级);② Runner 表格补 `.card`(BUG-UI-003 重开,首轮"vp 为裸表格"结论系定位偏差,vp L1572 有 .card,已更正留痕);③ 内容区页头 icon+标题+换行+说明(BUG-UI-004,初版误读为侧栏、后经用户澄清修正);④ 项目页保留右上角新建按钮(BUG-UI-005);⑤ 用户管理筛选栏与表格 0.0px 零间距(BUG-UI-006 实测)。另:补登记前轮中断会话遗留的 R2.F1(BUG-008/009 group_id 类型宽容,后端+专用测试已落地)。运行时证据:recon-*.png 截图 + Playwright 几何实测;分析见 `.scratch/fix-analysis-r2a.md` / `fix-analysis-r2b.md` | 用户 4 条 UI 修复指令(rd-fix 第 3 轮) |
| 2026-09-22 | **rd-fix 第 4 轮:新增 R2.F4 修复 BUG-010(已 verified 迁移 ISSUES.md)**。用户报告 test-connection 401 → 实测澄清:平台接口 HTTP 200 + code=0 鉴权正常,401 是 **GitLab 对已保存 bot token 的拒绝**经 data.message 透传(接口机制 = 取 DB 已保存的 gitlab_url+bot_token 调 `GET /api/v4/version`,gitlab_service.bot_test_connection;表单未保存的输入不参与测试)。真 bug 在前端:handleTestConnection 把响应 ok 硬编码 true,GitLab 失败也渲染成功样式误导排障。修复:`ok: res.data?.ok === true`。回归:tsc 零错误 + 页面实测失败场景(⚠ 401 文案失败样式,截图 fix-test-connection.png)。**附带发现(未修留观)**:平台设置页预览/部署域名回显值疑似密文(VLZ2…形),建议单查。**未提交,待用户确认** | 用户报告接口 401(rd-fix 第 4 轮) |
| 2026-09-22 | **rd-fix 第 5 轮收敛:BUG-012/013/011/009 全部 verified,迁移 ISSUES.md;BUG-009 全链路闭环**。① 用户 curl 指认 token 有效 → 实证 PAT 需 PRIVATE-TOKEN 头,gitlab_service.py 两处 Bearer 改 PRIVATE-TOKEN(R2.F5,BUG-012);② test-connection 端到端 ok=true(v11.7.0);③ 冒烟建项目发现私有组 internal 拒绝 → bot_create_repo 按组可见性自动降级(R2.F6,BUG-013);④ 冒烟项目 auto 建仓成功(GitLab repo 680)+ clone + push 全通 → **BUG-009 终验通过**;⑤ 浏览器复核 BUG-011:侧栏 12 项含 Skills 市场,点击直达渲染正常;⑥ 平台设置域名污染已清理(preview/deploy.zhanqirsj.com 占位,用户可改)。测试:pytest gitlab+project 66/66、tsc 零错误。**GitLab 环境备忘:仅 http;group 100 为 private**。冒烟项目 rd-fix smoke test(repo 680)保留可删。已提交推送(5bf7a07 等 6 笔) | rd-fix 第 5 轮收敛(用户指示 fix it) |
| 2026-09-22 | **rd-fix 第 6 轮:新增 R22.F1 修复 BUG-014(已 verified 迁移 ISSUES.md)**。用户报告 /manage/requirements 白屏崩溃(item.key.slice)→ 根因:dashboard_views 端点返回 req_id/task_id 与前端 DimensionItem 契约 key 不一致,列表恒空期未暴露,有真实数据即崩。修复:后端两端点 items 补 key 字段(前端零改动)。回归:pytest dashboard 8/8;API 实测 items 含 key;浏览器四维页全验不崩、行渲染正常(截图 fix-dimension-page.png)。**未提交,待用户确认** | 用户报告运行时崩溃(rd-fix 第 6 轮) |
| 2026-09-22 | **rd-fix 第 3 轮收敛:BUG-UI-001/003/004/005/006 全部 verified,迁移 ISSUES.md**。修复点 R19.F3(面包屑统一两级+父级可点击,用户决策优先于 vp)/ R16.F2(Runner 表格 .card 包裹)/ R2.F2(内容区 12 页页头 icon+标题+换行+说明;**解读修正留痕:初版误改侧栏,经用户澄清完整回滚**;工作台/项目加 icon、删项目页空态重复按钮为用户追加指令;平台设置/Skills 无 vp 原型文案自拟留痕)/ R2.F3(守卫型,按钮核实存在;删空态重复按钮)/ R19.F4(筛选栏归位 .fbar,0.0px 零间距消除)。回归:前端 tsc 零错误 + vite build 成功;Playwright 11 页断言全过(面包屑两级/卡片结构/页头 icon+sub/按钮唯一性/侧栏单行还原),截图 fix-admin-runners.png、fix-admin-users.png、fix-projects.png;后端 pytest 由并行会话完成第 3 轮回归(260/260,含 R2.F1 用例)。修复报告 `.scratch/rd-fix-r3/fix-report.md`。**未提交,待用户确认** | rd-fix 第 3 轮收敛 |
| 2026-09-23 | **rd-fix 第 7 轮:新增 R2.F7 修复 BUG-UI-063 详情页面包屑补全上级链**(用户指令:所有详情页面导航面包屑都带上上级;波及 R3 需求详情 / R4 任务工作台及子页 / R14 归档 / R20 知识库视图;实体名用页面已加载数据,不新增 API) | 用户指令(rd-fix 第 7 轮) |
| 2026-09-23 | **rd-fix 第 8 轮:本地 Runner 实测(用户指令:任务启动必须依托于容器启动,本地安装一个 runner 测试)+ 新增 R8.F1 修复 BUG-026**。环境动作:Docker Desktop 启动、docker SDK 安装、API 创建本地 Runner(local-win-test,plt-runner token 一次性)并启动 runner/ 进程——**注册成功**(register_success runner_id=88b6cb82);构建 devbox 镜像失败 → 实证 mcr devcontainer/universal 整仓退役(404)→ R8.F1 基础镜像切换 devcontainers/typescript-node:dev-bookworm(默认用户 codespace→vscode 适配;CRA 移除留痕) | 用户指令 + 实测发现(rd-fix 第 8 轮) |
| 2026-09-23 | **rd-fix 第 8 轮收敛:R8.F1/F2/F3 全部 verified,BUG-026~030 五连闭环,"任务启动依托容器启动"全链 E2E 打通**。① R8.F1(BUG-026):镜像四轮迭代构建成功——universal 退役→typescript-node、skills/ 占位目录补建、MCP npm 清单 5→3(server-git/sqlite 退役实证)、用户 node 适配、CMD sleep infinity(BUG-028);② R8.F2(BUG-027):events 线程泵送 + qicheng.managed 过滤——重启后心跳 30s 刷新、越权接管 0;③ R8.F3(BUG-029):clone 认证 oauth2 重试 + remote 洗净——私有仓库克隆成功且凭据 0 落盘;④ BUG-030(并入 R8.F3):handle_container_started 回填 tasks.container_id/runner_id(后端无 --reload 需重启加载,round4 实测回填成功)。E2E 证据:round4 容器 56f4510d340e Up + tasks 行三字段齐 + 双容器并行;E2E 过程中环境事实:项目并发上限 3(4003)、stop 接口回收死任务。**ISSUES 迁移留待与并行 rd-test 会话统一收口;runner/backend 改动未提交待用户确认** | rd-fix 第 8 轮收敛(本地 Runner E2E) |
| 2026-09-23 | **rd-fix 第 9 轮:新增 R4.F1 增强 BUG-UI-064 任务工作台三面板(用户指令:terminal/ai对话/文本编辑器全屏、保存、滚动)**。全屏 = TaskDetail 持状态 + 面板 CSS 提升 fixed 覆盖层(不重挂载,终端缓冲/聊天态/编辑器实例保留)+ Esc 退出;保存 = 编辑器工具栏显式保存(自动保存+Ctrl+S 保留)、终端日志导出 .log(xterm buffer 序列化,attachTerm 回传实例)、对话导出 .md;滚动原有链路验证健全。tsc 零错误 + build 8.25s;核对 `.scratch/R4.F1/ui-check.md`。**未提交待用户确认** | 用户指令(rd-fix 第 9 轮) |
| 2026-09-23 | **rd-fix 第 10 轮:新增 R4.F2 修复 BUG-UI-065 工作台缺陷批 + 四项 UI 增强(用户实测反馈:terminal 不行/编辑器底部贴边/diff 不行/对话框不行)**。探查实证:① vite 仅代理 /api,**/ws 无代理 → 终端 WS 全灭**(主因);② handleClose 双 setTabs 覆盖致 tab 关不掉;③ 查看 Diff 不设 diffPath;④ 发送无 pending 反馈。修复:/ws 代理、handleClose 重写、Diff 自动选首个变更+空态、发送转圈+"AI 处理中"提示;增强:编辑器状态栏(path/保存态)、左栏/右栏/终端条三处 useDragSash 拖拽、任务头 分支/容器/Runner chips。tsc 零错+build 9.47s。**⚠️ vite dev 必须重启加载 /ws 代理;未提交待用户确认**。后续 UI 建议留档:预览内嵌标签页/命令面板/Diff 同步滚动/布局持久化 | 用户实测反馈(rd-fix 第 10 轮) |
| 2026-09-23 | **rd-fix 第 11 轮:新增 R4.F3 对齐 BUG-UI-066 任务工作台 vp #/t/T-301 版式(用户指令)**。TaskDetail 重写:wb-head(返回+类型徽章+标题+状态+chips+acts)/ .wb 三栏(236/1fr/384,dev 非挂起才显文件树,保留左右拖拽)/ 中栏 twrap 卡片(tabs+状态栏)/ **右栏改 对话·终端·活动 Tab 组**(终端从底条变 Tab 全高,hidden 保活缓冲不丢)。R4.F1/F2 能力(全屏/导出/保存/状态栏)全保留。验证:独立测试账号(13900001111 邀请注册+editor 入项目,规避同账号并行登录互踢)Playwright 实测——结构断言全过、终端 Tab 内容器 shell 提示符可交互;pytest 之外 tsc 零错+build 22.5s。**未提交待用户确认** | 用户指令(rd-fix 第 11 轮) |
| 2026-09-23 | **rd-fix 第 12 轮:R4.F3 被用户打回("你完全不按这个 ui 来"),新增 R4.F4 照抄重写 BUG-UI-066**。一手证据:1600×900 并排截图(vp-T301-baseline.png vs react-task-before.png)——React 仍为三张圆角浮动卡片,非 vp 全出血工作台;根因 = R4.F3 只做"类名存在"结构断言、未做并排视觉核对,违反 vp-prototype-fidelity 纪律。R4.F4 规格:主 agent 一手通读 vp pageTask/centerPane/rightPane/treePane/chatPane/actPane + CSS 原值(L79-391/L1147-1483),TaskDetail 四类型分支全量照抄,CSS 原类名原值移植,并排视觉核对升级为硬门禁。**流程修正:验证报告必须含 vp vs React 同框截图,结构断言不再单独作为通过依据** | 用户打回(rd-fix 第 12 轮) |
| 2026-09-23 | **rd-fix 第 12 轮收敛:R4.F4 执行完成,BUG-UI-066 → fixed(并排视觉核对通过)**。编排异常留痕:三个实现 subagent 连续因上下文超限(autocompact thrashing)失败,按收敛保护切主 agent 直修(vp 已一手消化为自包含规格 `.scratch/R4.F4/vp-excerpt.md`)。改动:① TaskDetail.tsx 全量照抄重写(wb-head 五段+原值徽章/三栏 grid 无 gap 无 padding/twrap 三连/中栏五类型分支/右栏三 Tab+pulse dot/acts 按 vp 条件/tree-foot/sash 叠加边缘不进 grid 流);② globals.css 补齐 vp L326-391 类(wb-head/wb/col-*/empty/tree-tabs/ttab/chg-*)并逐值核对既有类;③ TestCasesReview/TestReport/DeployStatus 增 embedded 内嵌;④ 后端 GET /tasks/{task_id} 增 project_id/req_id(重启生效,面包屑数据源);⑤ **顺带修复 Breadcrumb override 从未生效的深层缺陷**(Provider 只包 Breadcrumb 自身,Outlet 在 context 外 → 改模块级桥),任务页四链面包屑真正渲染;⑥ smoke 任务乱码标题修正(本会话自建数据)。验证:tsc 零错 + build 成功;Playwright 并排核对 T-301 变体(种子 requirement/done 任务)+ dev/running 两态均与 vp 基准一致(vp 怪癖"非 dev 中栏落 236px 列"照抄,"chat pane 漏 on"不照抄已记录);功能扫测终端 WS 容器 shell/Tab 切换/@补全不回归。报告 `.scratch/R4.F4/ui-check.md`。**未提交待用户确认;test 账号 13900001111 密码已重置为 Rdfix1234(R4.F4 环境准备,留档)** | rd-fix 第 12 轮收敛 |
| 2026-09-23 | **增量3:PRD R23–R27 计划落盘(Q30–Q40 已确认;ARCH 快筛无需新增决策——R23 按 D9/D10 既有加密与 env 注入契约、R25 按 R19 audit 基建、R26 按 D6/D11/D13 既有 Runner/exec 协议、R27 按 R2 既有流程)。新增 5 分片 R23-R27;调研底稿 `.scratch/code-analysis/`(audit-inventory.md 44 挂点 / runner-terminal-admin.md;llm-chain.md 调研 agent 失败未落盘,已由主 agent 直查 llm_service/task_service 补齐,分片内 file:line 为准)。无新表、无 DDL(DEPLOY.md 零变更);新增错误码:2008(LLM 连通失败)/ 2011-2014(绑定细分)/ 6001-6003(Runner 终端)。自动确认:R23(依据 Q30-Q32 + resolve_config 单插入点实证)、R25(依据 Q35/Q36 + 44 挂点清单;三项端点不存在口径登记 ISSUES)、R27(依据 Q39/Q40 + 根因实证);R24/R26 含负向规格 3 项待拍板(R26 并发会话=1、runner.terminal_open 审计、R25 登录失败 detail 脱敏手机号),见待确认清单 | rd-plan 增量3 |
| 2026-09-23 | **增量3 计划确认收口**:Q-A 登录失败审计记脱敏手机号;Q-B Runner 并发会话上限=1;Q-C 记 `runner.terminal_open` 审计;Q-D 三个无宿主事件(登出/Runner 启用/强制 push)按"不接 + ISSUES 登记"口径确认。待确认清单清零,增量3 计划进入执行 | 用户确认 + 指令 /rd-dev |
| 2026-09-23 | **R23 完成闭环(增量3 首点)**。后端:SETTING_KEYS +llm_* 3 键(str 类型)+ 三键齐备校验、2008 连通测试钩子(校验→测试→落库顺序)、resolve_config 平台回退(source 字段)、GET resolvable 端点(project/platform/none);前端:admin.ts 类型、useResolvableModelConfig、模型 Tab 两态提示条。测试:新测 13 绿+1 跳过 + 存量 39 绿 + tsc 零错 + vite build 过 + 审计通过。**编排留痕**:QA/后端/前端/审计首批 4 subagent 中 2 个 autocompact 死亡且 2 个完成通知失真(与调研期 llm-chain 事故同因)——按 rd-fix 第 8/12 轮先例切**主 agent 直做后端**并重审;ground truth 一律以磁盘/git 为准。**决策留痕**:① PUT 响应键沿用既有 `updated`(分片 `updated_keys` 系笔误,测试对齐实现);② 平台保存连通失败用独立码 2008(项目级 13001 已被 R13 占用);③ 判据 #5 标 ◐:回退解析三态已单测,task_service:86-89 env 按 key 透传零改动,容器内真实 env 验证归 rd-test;④ 顺手修复工作树遗留编译错(Breadcrumb 死函数/ProjectDetail 未用导入/TaskDetail 断线驳回按钮——后者移除重复入口,驳回走 TestReport 面板既有交互,属 R4.F4 未提交遗留,vp 验收时留意) | rd-dev 增量3 R23 |
| 2026-09-23 | **R24 完成闭环(增量3 第 2 点)**。前端 `PlatformSettings.tsx` 重写:左导航 4 组(200px 定宽,active=bg-surface-strong+600+左 2px primary 竖线)+ 右单卡片(max-width 672px/.card 等值);三组既有逻辑平移,第 4 组模型默认配置接入(R23 契约)。验证:tsc 零错+vite build 过;Playwright 判据 1-7 全实证(4 项导航/默认组/672px/切换丢弃 100→999→100/掩码零回写 PUT body 实证/测试连接绿样式/防重 3 连点 1 PUT/缺项标红色值精确命中/R19 守卫弹回),ui-check 9/9 ✅。**编排留痕**:前端 subagent 派发 2 次均 autocompact 死亡,切主 agent 直做;subagent 死前初版遗留 10 项缺陷已全修(色板无 error/success、语义色子键 tx/bd→fg/border、打码串回写、gap/行距偏差、导航默认态文字、缺项未标红、受控切换警告、同 tick 防重失效、注释 `*/` 早闭、保存后未刷新打码)。**决策留痕**:① 分片"路由 /admin/settings"系笔误,沿用现状 `/admin/platform-settings`(复用清单"admin 路由不变"优先);② 敏感键 readOnly+「更换/取消」机制:分片④ readOnly 的必要补全(否则无法更新密钥),payload 剔除未编辑敏感键——**顺带修复原版即存在的打码串回写覆盖真值缺陷**(后端无掩码跳过逻辑,PUT 直存加密);③ GitLab 组提交键集合含 gitlab_webhook_secret(4 字段平移,分片键集合漏列第 4 键);④ 导航容器 border/rounded-lg/p-2 为规格外最小视觉补值(分片仅给 bg-surface);⑤ 保存成功后静默 GET 刷新打码回显;⑥ 消息条按分片"表单上方"字面移出 form(compareDocumentPosition 断言 banner 在 form 前,输入保留)。**未提交待用户确认**(连同 R4.F4/R23 遗留) | rd-dev 增量3 R24 |
| 2026-09-23 | **rd-fix 第 14 轮:新增 R5.F1 修复 BUG-032(对话不可用)/BUG-033(files/changes 间歇 500)**。用户报障"对话部分没有用"。一手实证:① runner 日志 45min 内三次掉线(13:12/13:40/13:55,`ConnectionClosedError: no close frame`+写侧 10053);② 根因四层——runner 事件循环被同步 `claude_prompt` 阻塞致 ping/心跳饿死(服务端杀连接+sweep_offline 注销活连接)、5 路 send 无锁并发帧交错、平台 `request_runner` 死连接 send 静默成功致 future 永不结算(用户"发送中"卡 10 分钟)、`send_message` 先落库后校验失败回滚消息不入库;③ 上轮分析底稿的 sweep_offline 机制经本轮代码核实成立并合并。修复:runner send 加锁串行化 + claude_prompt 移入 to_thread + send_result 防炸;平台 request_runner 快速失败(转既有 TimeoutError 路径)+ send_message 校验前移(上轮 P0 落地)。分析底稿 `.scratch/fix-analysis.md`(含上轮归档);分析 subagent autocompact 死亡,按第 8/12 轮先例主 agent 直查 | 用户报障(rd-fix 第 14 轮) |
| 2026-09-23 | **rd-fix 第 14 轮收敛:R5.F1 执行完成,BUG-032/033 → fixed**。改动:① runner/main.py 全局 `_SEND_LOCK` 串行化 5 路 send(并发帧交错致 RST 掉线)+ `claude_prompt` 移入 `asyncio.to_thread`(同步 docker exec 堵死循环→ping/心跳饿死,实测 claude 执行中第 4 次掉线复现根因)+ `safe_send_result` 防炸;② backend request_runner:send 异常即时转 TimeoutError(死连接 600s 死等→秒级 9001)+ asyncio.TimeoutError 归一化内建 TimeoutError(**py3.10 两个类,`except TimeoutError` 从未接住——BUG-033 的 500 真身**)+ send_message 容器/runner 校验前移(失败不再回滚用户消息)。E2E 全判据过:真实消息 174s 全链路 200+落库/离线 0.06s 返 9001/changes 3×200/295 测试绿。**新发现 BUG-034(open)**:AI 回复=ECONNREFUSED——容器内回环 base_url 注入(已修 container_base_url 改写)+ 本地 LLM 代理 18765 未监听(用户待办:启动代理监听 0.0.0.0 或改配置)。runner env 备份移至 `~/qicheng/runner_env.txt`(仓库外,token 卫生);backend/runner 日志落盘 `.runner_restart/`;浏览器 UI 复验因 Playwright profile 锁未完成待补 | rd-fix 第 14 轮收敛 |
| 2026-09-23 | **BUG-034 闭环(用户配置全局默认 LLM 后重启任务)**。用户设全局 LLM=token-console.zhanqitv.com.cn(qwen3.7-plus)→ 停旧任务 + 新建 dev 任务(创建即拉起,resolve_config 取新配置)→ E2E 暴露第三层:**claude CLI 不读 LLM_MODEL,读 ANTHROPIC_MODEL**,缺失时请求内置 claude-opus-5-5 被网关 503——task_service 两处 env 补 `ANTHROPIC_MODEL` 注入。另:并行会话 R25 重构删除了 users_admin.set_audit_session_factory 但 main.py:108 调用未同步清理,后端启动失败,已移除死调用。最终验证:新任务 4a64b4ae(容器 15a50a94bdfc)对话 **5.1s 返真实 AI 回复**并落库——对话链路(前端→平台→Runner→容器 claude→网关→落库→前端)全通;旧任务 7531a151/d0713572 已 cancelled | 用户指令"用全局默认 LLM 重启任务" |
| 2026-09-23 | **R25 完成闭环(增量3 第 3 点)**。44 项审计挂点:**43 接入 + 1 无宿主**(invitation.consume,函数无调用方→ISSUES 第 4 条)。改动:auth_service(登录 6 事件:成功/4 类失败,失败走 spawn 独立会话防业务回滚连带、成功走事务内 audit_write;占位全零 user_id+anonymous)、terminal_service(TODO 清除+破坏性命令 spawn,TerminalConnection 加 role 字段)、project/project_member/model_config/requirement/task 5 个 service(模式 A 事务内)、users_admin/runners/platform_settings/tasks/requirements 5 个 API 层(模式 C,service 签名不改)、2 个系统 sweep(占位+system+不记 ip)。验证:新增 pytest 19 例(P0 9+P1P2 10)全绿;**最终全量 293 passed+1 skipped 零回退**;真实环境 API 实证(超管过滤 3 行新事件/普通用户 403/占位 uid+anonymous+ip 全对)。**顺带修复 R19 既有缺陷**:users_admin `_session_factory_holder` 无任何注入调用方→user.disable/enable 审计此前从不落库,改直连模块级 factory。**编排留痕**:P0 subagent 派发 1 次中途失真(返回截断为过程叙述,只落一半)→ 主 agent 直做;首次全量回归抓出 create_project 插桩 NameError(name 变量不存在→project.name)已修。**调研底稿缺失**:`.scratch/code-analysis/audit-inventory.md` 丢失→实施期间重建 `audit-inventory-rebuilt.md`(43+1 逐项 file:line/detail 载荷)。**决策留痕**:① 无宿主第 4 项 invitation.consume 同口径登记;② 登录失败口径=action_type 描述失败原因(达阈值分支记 wrong_password+locked_triggered 而非 locked);③ 系统事件命名 task.timeout_sweep/runner.offline_sweep(分片未定名);④ detail 不落平台设置"值"只记键列表;⑤ 判据 9 页面级走查因浏览器与并行会话共享实例被扰,API 断言替代,页面走查归 rd-test。**未提交待用户确认**(含 R4.F4/R23/R24 及并行 rd-fix 第 14 轮 R5.F1 改动,提交时建议按需求点分笔) | rd-dev 增量3 R25 |
| 2026-09-23 | **R26 完成闭环(增量3 第 4 点)**。后端:ErrCode 6001-6003(runners.py 四段校验 404→online→无活跃 shell 会话(closed_at IS NULL)→self_container_id)、POST /api/admin/runners/{id}/shell-sessions(exec 复用下发 + runner.terminal_open 审计)、TerminalConnection.task_id 可空化(逐引用点核对)、runner/main.py register 自报 HOSTNAME;破坏性命令 detail 加 session_kind(runner_shell/task)。前端:RunnerManagement 操作列「终端」按钮(online 可点/置灰 title)+ 80vw Dialog 嵌 TerminalPanel(先建会话后渲染,6001/6002/6003 文案 Dialog 内呈现,关闭调 DELETE close 销毁)、Terminal/TerminalPanel 加可选透传 props。验证:新增 pytest 10 例全绿(四段校验/403/审计两事件/task_id 解耦/session_kind 标记);全量 303 passed+1s 零回退;浏览器实证按钮态+Dialog 标题+6003 文案全链(截图 r26-shell-6003-dialog.png);本地 runner 重启后 self_container_id 上报实测。**编排留痕**:后端 subagent 派发 1 次 autocompact 死亡(死前落盘 6001-6003 错误码+task_id 解耦)→ 主 agent 接管余下全部。**决策留痕**:① Terminal.tsx/TerminalPanel.tsx「零改动」与判据 11「不重连」冲突→最小破例加可选 props(默认不传=既有行为);② 6002 用台账表判定非内存注册表;③ 库 online 但连接缺失同 6001;④ Windows 裸跑 HOSTNAME=空串与"非容器 id"同落 6003 兜底;⑤ ws_url 不带 ?token=(与 terminal.py 现状一致);⑥ 走查前重启旧后端进程加载新路由。**遗留**:判据 4/8/11 真实 pty 交互/kill/断线场景需容器化 runner,归 rd-test。**未提交待用户确认** | rd-dev 增量3 R26 |
| 2026-09-23 | **rd-fix 第 15 轮:5 修复点执行完成(R1.F2/R2.F8/R22.F2/R3.F1/R8.F4),BUG-UI-067/068/069 + BUG-035/036 → fixed**。① R1.F2:登录页删 4 段演示/技术文案,auth 四页 LOGO 统一 AuthLogo 组件居中(偏差 0.0px);② R2.F8:ProjectList 卡片 hash→useNavigate(BrowserRouter 下原写法不跳),12 页补 page-head icon 惯例(留痕:路由实为 /settings/gitlab-token,分片笔误);③ R22.F2:四维页重写为 audit-logs 范式(card>fbar→tbl→card-foot,各维列照抄 vp heads 逐字)+ QuickCreateDialog(项目→关联字段)+ dashboard_views 两接口扩 project_id/q 参数与 req_branch/runner/created_by/端口/用例字段(批量摘要防 N+1),收敛 open 批 052/053/054/055/059/060/061/062;④ R3.F1:**E2E 推翻静态"链路完整"结论——create_polish_task 从不 INSERT tasks 行**(前端跳转 404/容器回填落空/四维不可见),补先落 Task(pending)再调度、成功置 running;⑤ R8.F4:custom_env_vars(envmap 键:保留名拒写/≤50/值≤2048/不打码决策留痕)+ task_service 两链 env 铺底注入 + LLM_URL 别名;PlatformSettings 第 5 组 KV 编辑。验证:Playwright 独立 headless 41/41(并排截图 login/manage 四维);新 pytest 13 例 + dashboard 8 例;**真实容器 env 实证** MY_TEST_VAR/LLM_URL 在列(docker exec 50f386fa63b4);tsc 零错+vite build 过。**环境留痕**:测试库 tasks 缺 claude_session_id 列(并行 R9.F1 迁移记账漂移)手工补列;8000 端口滞留旧进程曾致修复未生效假象(强杀重启后实证);取消 2 条修复前遗留 polishing 需求。**未提交待用户确认**;最终全量 pytest(干净窗口)= **322 passed + 1 skipped**,3 个 test_auth_login teardown 1213 死锁经隔离重跑 12/12 全绿,判定共享测试库并发噪声(第 15 轮 4 项环境留痕之一,详见 `.scratch/rd-fix-r15/fix-report.md`) | rd-fix 第 15 轮收敛 |
| 2026-09-23 | **rd-fix 第 15 轮追加:新增 R9.F1 修复 BUG-037(任务页终端自动进入 claude 与对话同一会话)**。用户指令第 6 条。一手证据:对话=逐条独立 `claude -p` 调用(claude_service.py:60,无 --session-id/--resume,对话自身无上下文延续);任务终端 exec 下发裸 `/bin/bash`(terminal.py:103-109);Runner 侧 claude_prompt 自拼 cmd(container_manager.py:350,Runner 独立进程不可 import 后端)。方案:tasks 加列 claude_session_id(uuid4 懒生成,对话/终端先到先建);首次 `--session-id` 固定 UUID、后续一律 `--resume`(规避 CLI 版本对"复用 --session-id"的语义差异);终端 exec 改 bash -lc 包装(claude 缺失时落 bash、退出 claude 落回 shell);R26 超管 Runner 终端链路零波及。分析 `.scratch/fix-analysis.md`,分片 `./DEVPLAN/R9.F1.md` | 用户指令(rd-fix 第 15 轮追加) |
| 2026-09-23 | **R9.F1 执行完成,BUG-037 → fixed(第 15 轮追加指令闭环)**。实施:① tasks 加列 claude_session_id(模型 + alembic 迁移 a7b2c8d9e1f3,链验证无分叉);② ensure_claude_session 懒生成(uuid4,对话/终端先到先建);③ send_message→run_prompt 透传 session_id/resume,runner claude_prompt 拼 --session-id(首次)/--resume(续接),不传参数时 cmd 与原版逐字节一致;④ 终端 exec 改 bash -lc 包装(command -v claude 守卫:无 claude 容器直接落 bash;退出 claude 落回 shell);⑤ 语义安全:仅首次用 --session-id、后续一律 --resume,规避 CLI 版本差异。验证:新增 backend 6 用例 + runner 3 用例;R9.F1 触碰面四文件隔离跑绿(r9f1 6/6×3 复跑);runner 全量 24/24;全量回归残 fail 经隔离复跑+git diff 归因为 R25 审计 FK 死锁 + 共享远程测试库并行串台(两轮全量失败集 8/63→17/87 漂移为铁证),R9.F1 触碰面零失败。连带修三处过时测试替身(tasks_api/dev_tasks fake_run_prompt 形参、terminal_api 夹具补 Task 行 + cmd 断言)。**verified 待用户真实容器浏览器实测**(终端自动进 claude TUI → 对话后终端 resume 同会话上下文 → 退出落 bash → R26 Runner 终端不变)。未提交待用户确认 | rd-fix 第 15 轮追加收敛 |
| 2026-09-23 | **新增 R2.F9 修复 BUG-038(GET /api/admin/platform-settings 500)**:全库 5 条存量密文(platform_settings 3 + users 1 + model_configs 2)与当前 PLATFORM_SECRET_KEY 全部 InvalidTag,根因 09-22 23:03 .env 密钥轮换后长驻 uvicorn 未重启仍用旧密钥写库至 09-23 14:45,20:33 重启载新密钥解存量即崩;_decode_stored 无逐键容错,单条坏行打挂设置页。方案:_decode_stored 单文件逐键容错折叠 None,消费方经既有 2001/13005 干净降级,0 前端;编号 R2.F9(顺延,R2.F8 已被第 15 轮 ProjectList 修复占用,无分片文件仅存变更记录)。分析底稿 .scratch/fix-analysis.md,分片 ./DEVPLAN/R2.F9.md | 用户实测(rd-fix 第 16 轮) |
| 2026-09-23 | **增量4:PRD R28–R30 计划落盘(Q41–Q43 待确认;ARCH 快筛无需新增决策——R28 按 R1 既有用户体系扩展、R29 按 R21/R22 既有聚合视图复用、R30 纯前端 CSS 变量切换)。新增 3 分片 R28(用户信息修改增强:users 表加 avatar_file_path + POST /api/users/me/avatar + GET /api/files/avatars/{filename} + 前端头像上传组件)/ R29(平台导览:TourDialog 组件 + 步骤动态生成 + localStorage 首次弹出 + 侧栏入口接线)/ R30(黑白主题切换:[data-theme="dark"] CSS 变量 + useTheme hook + 顶栏切换按钮 + 系统主题监听);调研底稿 `.scratch/code-analysis/increment4-analysis.md`。R28 有后端(1 新接口 + 1 扩展接口 + users 表 1 字段),R29/R30 纯前端。无新表、无 DDL(users 加字段走 alembic)。R28/R29/R30 自动确认依据:复用现有接口/组件/样式体系,无负向规格缺口。**待确认 3 项**:Q41 头像存储路径、Q42 导览步骤接口策略、Q43 暗色主题参考风格 | rd-plan 增量4 |
| 2026-09-23 | **R2.F9 执行完成,BUG-038 → verified(第 16 轮闭环)**。QA 红测先行:9 failed 复现 InvalidTag(证据 /tmp/bug038_red.txt)→ 修复转绿 11/11;改动 2 文件:platform_settings_service.py(+15/-2,_decode_stored 逐键容错捕获 InvalidTag/ValueError 折叠 None + warning 只记键名不泄明文)+ 新增 tests/test_bug038_invalid_secret.py(11 用例:GET 200/失效键缺席/日志不泄密/test-connection 2001/resolve_config+resolvable 13005/PUT 重录自愈/无辜路径防误伤)。回归:targeted 76+1s、110 消费方全绿;全量 333 passed/1 skipped/0 failed。真实环境(用户确认重启后):超管 GET /api/admin/platform-settings = HTTP 200 + code 0,gitlab_webhook_secret/gitlab_bot_token/llm_api_key 降级未配置形态,日志 3 条 warning 精准命中,重启后 0 个 500;BUG-038 迁移 ISSUES.md,BUGS.md 活跃代码 bug 清零。**环境留痕**:① venv 缺 pytest,补装时 pytest-asyncio 1.4 与 conftest session event_loop 不兼容,回 pin pytest 8.4.2+pytest-asyncio 0.26.0(仅 dev 依赖);② 旧 JWT 因 token_version 递增失效属既有机制,重启后浏览器需重新登录。**运维重录项(归用户)**:platform_settings 3 键 + users.gitlab_token 1 条 + model_configs 2 条(同根因失效密文,旧密钥不可恢复) | rd-fix 第 16 轮收敛 |
| 2026-09-23 | **新增 R19.F5 修复 BUG-039(审计日志接口返回空)**:用户报告审计日志没有/接口返回空;实证后端正常(裸调 63 条今日事件,含 platform_settings.update×2),根因在前端——AuditLogsPage 时间筛选 toISOString() 发 UTC 串,而 audit_logs.created_at 存本地(UTC+8)裸墙钟,end_time 落后 8h 把全表滤空(复放矩阵:仅 end_time=UTC→total 0,本地串→65)。修复:前端单文件改本地裸时间串(顺带修 8h 显示偏移 + 清空输入 RangeError)+ isError 分支 + start>end 禁查询(R19.F2 规格缺口收口);0 后端。分析底稿 .scratch/fix-analysis.md,分片 ./DEVPLAN/R19.F5.md | 用户报告(rd-fix 第 17 轮) |
| 2026-09-23 | **R19.F5 范围修订(用户指令)**:平台默认时区显式钉死东八区 GMT+8——前端时间源显式 Asia/Shanghai(不跟随浏览器,toISOString/toLocaleString 无参形式均弃用,时间列直接渲染后端裸串);后端 database.py 引擎加会话级 time_zone='+08:00' 固化 func.now() 写入契约(存量数据已实证 +08:00 墙钟,零迁移);新增强制非 GMT+8 浏览器时区的回归判据 | 用户指令"修改默认时区为东八区 GMT+8"(第 17 轮执行中) |
| 2026-09-23 | **R28 执行完成(增量4 第 1 点)**:后端(users 表加 avatar_file_path + POST /api/users/me/avatar + GET /api/files/avatars/{filename} + PATCH 扩展) + 前端(ProfileSettings 头像上传组件 + MainLayout 头像显示改造 + users.ts/client.ts API 扩展)。验证:后端 57/57 pytest 通过(含新增 25 用例 + 17 补丁用例);前端 tsc 零错误 + vite build 通过;ui-check 8/8 ✅;审计发现修复 F1(昵称清空链路)/F5(setUser(null))/F6(外部 URL 同步清 avatar_file_path)。**编排留痕**:后端/QA/前端/审计 4 subagent 全部存活完成;DEPLOY.md 补记迁移 b2e8f4a6c9d1(并行会话第 17 轮已代执行到 dev 库)。**遗留**:前端 Playwright 走查归 rd-test | rd-dev 增量4 R28 |
| 2026-09-24 | **R27 执行完成(代码侧,增量3 收官点)**:① 后端——response.py 新增 2011-2014 + 2002 语义收窄为"URL 格式非法";gitlab_service bot_get_repo_by_path 按 status_code 细分(404→2011/401,403→2012 归并防枚举/其他+httpx 异常→2014)、bot_check_repo_permission 重写为 max(project_access, group_access)≥40(permissions 及两层各自 null 安全);project_service create_project manual 分支与 add_repo 同口径自动生效;② tdd——QA 红测 18 用例(Red 17 failed 实证)→ Green 全绿;既有 test_projects_api 404 场景断言 2002→2011 同步;相关回归 41/41 + Spec 轴独立复跑 43 passed(全量归 rd-check);③ 收口 code-review 双轴(工作区 vs HEAD 19095ff):0 硬违规,4 判断题裁定留痕(.scratch/R27/audit-review.md)——2002 文案字面 `{host}` 保持规格原文(插值仅 2011 系规格明文)、四步校验两处同形不提取(既有形状)、add_repo 错误码覆盖 2/5 接受(单函数共享路径)、MSG_* 文案常量新模式采纳;R27.md L121 双版 2014 文案括注标注作废(以枚举表为准);④ **判据 5(Q39 真机复现)被环境阻塞**:E2E 三场景均 2001 前置短路——gitlab_bot_token 存量密文 InvalidTag(R2.F9 遗留运维项,归用户重录),未触达新错误分支,创建无落库残留,后端已运行当前代码(PID 14516);证据 .scratch/R27/e2e-real-machine.md。**决策留痕**:红测 gitlab_bind_type 响应字段断言与分片"成功结构不变"冲突→以分片为准改查落库 project_repos(语义等价)。**状态 🔄:代码侧 5/6 判据 ✅,待用户在平台设置页重录 GitLab bot token 后复验判据 5 即转 ✅** | rd-dev 增量3 R27 |
| 2026-09-24 | **增量4 待确认清单清零(Q41–Q43 自主确认)**:用户直接进入 /rd-dev,按自主模式采纳当前推荐方案——Q41 头像存储 `./data/avatars/{user_id}/` + 公开 files 接口(R28 已按此实施,留痕);Q42 导览复用现有接口前端并行取第一条(与分片契约一致);Q43 暗色主题采用 GitHub Dark 风格(语义色徽章不随主题变,R30 执行)。均为计划期已给出推荐值的纯技术选型,无资损/不可逆风险 | rd-dev 增量4 R29 启动前 |
| 2026-09-24 | **R29 执行完成(增量4 第 2 点)**:① 新增 `frontend/src/hooks/useTourSteps.ts`(链式取数 项目→需求→任务∥归档,react-query enabled 串联 + retry:false 每维独立降级 + staleTime 60s 缓存;任务按 type 筛 dev/test/release;编号 1-N 动态重排);② 新增 `frontend/src/components/TourDialog.tsx`(复用 ui/Dialog:遮罩 bg-black/50=分片 rgba(0,0,0,.5)、p-6、shadow-lg、Esc、滚动锁;inline 覆盖 width 480/圆角 0.5rem/tourIn 动效 translateY 10px→0 0.3s ease-out;完成/跳过写 `tour_completed`,遮罩关闭不写);③ MainLayout 接线(首次自动弹出 useEffect + 侧栏按钮常驻 + 条件挂载 + 标题补 Play 图标对齐 vp DOM);④ globals.css 补 .tour-dialog 样式块(步骤 8px12px/12px muted→hover #09090b/.n 15px 圆形/列表 max-height 400px) + **reduced-motion 全局压制按 vp 原文补齐**(558 行空壳块填 `*{animation:none!important}`,审计建议采纳项)。验证:tsc --noEmit 0 错、vite build 过(26.55s)、判据 1-10 Playwright 全过(判据 9 用 route.abort 真拦截:6 步→4 步)、审计 0 阻塞 4 建议(采纳 1 拒 3,理由留痕 R29.md)。**编排留痕**:前端 subagent autocompact 死亡→主 agent 直做(第 N 次同因,先例 rd-fix 8/12、R23/R24/R26);QA subagent 首轮判据 9 用无数据场景替代 API 失败,发回补 route.abort 真拦截后达标;QA/审计 subagent 均存活。**决策留痕 9 条**见 .scratch/R29/ui-check.md 第四节(要点:遮罩复用 ui/Dialog 弃 .modal-mask;分片契约 `{list}` 系笔误实为 `{items}`;"并行 5 维度"字面与契约矛盾实作链式依赖;新用户渲染编号 1/2/3 系动态重排非缺陷)。**未提交待用户确认** | rd-dev 增量4 R29 |
| 2026-09-24 | **R30 执行完成(增量4 收官点,全计划 30/30 需求点代码侧完成)**:① globals.css 新增 `[data-theme="dark"]` 块(GitHub Dark 原值照抄分片;语义色/终端变量刻意不覆盖)+ 硬编码 #fff 定点覆盖 14 处(风险清单逐项处置)+ body/topbar 0.2s 颜色过渡(reduced-motion 既有块自动压制);② 新增 `hooks/useTheme.ts`(首次访问不落盘跟随系统、切换才持久化、监听 handler 内实时复查 localStorage——修正分片示例"effect 无条件写"与交互规则表矛盾,留痕);③ MainLayout 顶栏铃铛后插切换按钮(icon-btn 30px 与铃铛一致,moon/sun 15px,title 文案按分片)。**意外收获(顺带修复存量缺陷)**:vp 移植区 `.btn{background:var(--surface)}`(未分层靠后)压掉 @layer 内 `.btn--primary` 的 bg-primary——亮色下主按钮一直白底白字(TourDialog「完成导览」不可读,computed style 实证),补 `.btn.btn--primary` 高特异性两行恢复;另修铃铛下拉 `var(--card-bg,#fff)` 未定义变量恒白底。**关键技术坑(留痕)**:R30 块首版误入文件尾 `@layer base` 闭括号内,定点覆盖输给 components 层致暗色主按钮白字——移出 layer(未分层恒优先)后修复。验证:tsc 0 错 + vite build 过(22.07s)+ Playwright 判据 1-11 实测全过(判据 2/5 用 emulateMedia、9/10 代码级/变量级、真实容器渲染归 rd-test);截图 dark/light-dashboard.png;档案 `.scratch/R30/ui-check.md`(决策留痕 9 条)。**编排留痕**:QA/前端 subagent 2 派 2 死(命名 agent 需 tmux / autocompact),主 agent 直做。**未提交待用户确认**(工作区混有 R29/品牌更名未提交改动,提交建议分笔) | rd-dev 增量4 R30 |
| 2026-09-24 | **rd-fix 第 16 轮:新增 R2.F10 修复 BUG-049(用户实测:项目卡片需求数/成员数不对)**。根因:卡片为 R1 期演示数据——前端硬编码「0 个需求」+「罗/王/张」假头像,后端 list_projects 只返回 repo_count;修复=R2.F10=list_projects 批量补 req_count/member_count(分组查询防 N+1)+ 前端换真实数据(头像栈=owner 真实首字/色 + 成员数) | 用户指令(rd-fix 第 16 轮) |
| 2026-09-24 | **增量5 R31 实现闭环(rd-dev)**:3 subagent(QA/后端/前端)全部 autocompact 死亡 → 半成品可用(api/hooks/红测),主 agent 接管补齐(local_runner_service/4 端点+DELETE 代停/迁移 c7d3e9b5a2f4/runner_shutdown 分支/前端按钮三态+chip+双 Dialog)。**实现决策留痕**:① start/restart 内部重新生成 token(bcrypt 不可逆无法复用明文;明文仍不可见,符合 Q57);② spawn 前显式 commit(子进程 ~1s 即 register,独立会话须见已提交 hash);③ spawn 路径仓库根解析 parents[3](E2E 首跑 16002 code_missing 暴露);④ QA 红测 3 类机械缺陷修正(DB 断言改走 db_session 同会话——client override 不 commit;403 测试占位注册吃 bootstrap;remote-16001 用例按 R16.F3 造真实容器行)。验证:pytest 28 passed+1 skip、runner 34 passed、回归子集 58 passed;真机 E2E 创建→online/停止→进程退出/重启/start 幂等/删除→行删+二删404;审计 detail 无 token。**未提交待用户确认** | rd-dev 增量5 R31 |
| 2026-09-24 | **增量5 R31 计划落盘并确认(rd-plan)**:R31 Runner 本地快速创建与本机生命周期管理——平台 spawn 本机 runner 子进程(一键创建+启动,token 不可见)、`is_local` 标记、指令式停止(WS runner_shutdown;5s 超时强杀需句柄)、重启、**删除代停**(仅本机 runner:先停全部容器=R4 强制 push 链 → 停进程 → 删记录,失败中止;远程 16001 语义不变)、环境四项点击时校验细分文案、上限 3。分片 `DEVPLAN/R31.md`(格式自检 6/6 过);**自动确认依据**:接口/表/协议全在既有体系顺延(runners 加 1 列、4 新端点+DELETE 改造、runner 侧 +1 消息分支),复用 request_runner/request_stop/Dialog/审计模式,实施轨1 零新 UI 规范;**人工确认 Q A1–E1 全部按推荐值确认**(不改远程创建端点名称校验/push 同链/超时 10s·5s·30s·60s/disabled 仅删/平台地址默认 127.0.0.1:8000 已知限制)。PRD R31 同步置已确认 | rd-plan 增量5 |
| 2026-09-24 | **品牌更名「旗程」→「旗橙」+ Logo 换橙子**(用户定案):vp LOGO 常量三段升旗→橙子(径向渐变果身+绿叶短梗+高光),favicon/侧栏/登录页/auth 四页/浏览器标题全部同步;新增 `components/OrangeMark.tsx` 公共组件,AuthLogo/MainLayout 引用;后端网关错误页/OpenAPI 标题/日志/钉钉消息文案同步;vp 登录页品牌标语"一路旗程"→"一路旗橙"(保留原句式) | 用户指令 |
| 2026-09-24 | **rd-fix 第 18 轮:新增 R28.F1 修复 BUG-040 个人设置入口断链**(用户报障"用户头像编辑没有实现么")。核实:R28 头像编辑功能已实现(/settings/profile 上传/移除/预览齐全)但 **UI 零入口**——侧栏无个人设置组、顶栏用户下拉仅「退出登录」,普通用户只能手敲 URL;同断链波及 /settings 三页(个人资料/GitLab Token/通知设置);vp 原型语义(用户按钮 title「个人信息 / 退出登录」+ L1734「未绑定将引导个人设置」)本含该入口,React 版漏接(同 BUG-011 入口断链模式)。方案:用户下拉补「个人设置」菜单项(单入口经 SettingsLayout 左导航可达三设置页),分片 ./DEVPLAN/R28.F1.md | 用户报障(rd-fix 第 18 轮) |
| 2026-09-24 | **R28.F1 执行完成,BUG-040 → fixed**:MainLayout 用户下拉补「个人设置」菜单项(复用已导入 Settings 图标 15px + 既有 .user-menu-item 样式,零新增 CSS,置于退出登录上方;点击收菜单 + navigate /settings/profile)。Playwright 实测:下拉两项(["个人设置","退出登录"])→ 点击达 /settings/profile 且「上传头像」控件在(R28 可达性闭环)→ SettingsLayout 三设置页(个人资料/GitLab Token/通知设置)全可达 → 退出登录项回归无损;tsc 0 错 + build 26.49s;截图 .scratch/R28.F1/profile-reachable.png。**实施留痕**:超小修复(单文件 +10 行)按 subagent 必死先例(本会话 2 派 2 死)主 agent 直修。**verified 待用户浏览器复验** | rd-fix 第 18 轮收敛 |
| 2026-09-24 | **R26.F1 执行完成,BUG-041 → verified 迁移 ISSUES.md**:① 根因——runner/main.py 以 `HOSTNAME` 环境变量自报自身容器 id,Windows 裸跑(local-win-test)无此变量→空串,runners.py:176 与"旧版镜像无键"折叠同落「版本过旧,请升级 Runner 镜像」文案,误导排障(6003 拦截本身是 R26 决策④正确设计:裸跑无自身容器,exec 不可执行);② 修复——runners.py 校验段按上报形态细分 message(键缺失=版本过旧 / 空串=该 Runner 未运行在容器中(非容器化部署)),错误码 6003 不动、0 前端(Dialog 直显后端 message,RunnerManagement 仅注释引用),response.py 枚举注释同步;③ 验证——tdd Red(新增空串用例失败实证)→Green,test_r26_runner_shell.py 11/11 全绿(波及面 grep 实证仅此一文件);后端旧进程(PID 69808,无 --reload)重启加载新代码 health 200,**真机接口复验**超管登录调 POST /shell-sessions 返回新文案。**用户侧口径**:本地 Windows runner 裸跑无容器,Runner 终端按设计不可用;如需终端请容器化部署 runner;裸跑宿主机 shell 属新能力走 /rd-prd | rd-fix 第 18 轮收敛 |
| 2026-09-24 | **rd-fix 第 19 轮:新增 R16.F3 修复 BUG-042 删除 Runner 被孤儿容器行卡死**(用户实测:DELETE runner 返回 16001"Runner 上有运行中的容器,不可删除",但容器关联任务已 cancelled/done)。根因:delete_runner 只看 containers.status IN(creating,running),不联查任务状态;任务取消链路缺容器状态回写(既有缺陷源,登记 ISSUES 不混入本轮),孤儿容器行把删除永久卡死。**用户口径:任务不是进行中可以删除**——拦截收窄为容器(creating/running)且关联 Task.status='running'(项目既有"进行中"统一口径);部署容器 task_id NULL join 不上自然放行。分片 ./DEVPLAN/R16.F3.md | 用户报障(rd-fix 第 19 轮) |
| 2026-09-24 | **R16.F3 执行完成,BUG-042 → fixed**:delete_runner 拦截条件收窄——`containers(creating/running) JOIN tasks WHERE tasks.status='running'`(项目"进行中"统一口径,与禁用用户取消任务/超时清扫同款);任务非 running 的容器行与 task_id NULL 部署容器放行;16001 文案同步为「Runner 上有进行中任务的容器,不可删除」。tdd:新增用例(cancelled 任务容器 + 部署容器 → 放行)Red 实证 → Green;既有 16001 用例更新为关联 running Task(语义变更合法同步);test_runner_admin.py **11/11 全绿**;py_compile 零错;后端重启加载新代码(health 200)。**真机删除复验留用户**(不可逆管理动作不代执行)。**顺带登记 ISSUES**(治本项不混入修复):任务取消/完成链路缺容器状态回写(containers.status 滞留 running),是孤儿容器行的产生源头 | rd-fix 第 19 轮收敛 |
| 2026-09-24 | **rd-fix 第 20 轮:新增 R31.F1 修复 BUG-043 本机/非容器 Runner 无终端**(用户第三次报障:R31 本机 runner 1495a9d0 开终端 6003「非容器化部署」)。定性:非回归,是 R31 把本机裸跑 runner 变成一级能力后的**终端通道能力缺口**(R26 终端=exec 进自身容器)。方案:**宿主 shell 降级通道**——runner/terminal_manager.py 增 HostSession(subprocess,Windows=cmd.exe/Linux=bash,复用批量输出/写探测/kill 语义,resize no-op)+ main.py exec 哨兵 container_id="__host__" 分流 + runners.py 空串分支不再拒绝改为建 host 会话(键缺失仍 6003 版本过旧);终端 WS 转发/审计链路复用(session_kind=runner_host),前端零改动;Windows 管道模式无 pty(resize/真 TTY 降级)留痕接受。安全留痕:超管专用入口 + runner.terminal_open 审计,与 R31 平台 spawn 进程权责一致。分片 ./DEVPLAN/R31.F1.md | 用户报障(rd-fix 第 20 轮) |
| 2026-09-24 | **R31.F1 执行完成,BUG-043 → verified 迁移 ISSUES.md**:① runner/terminal_manager.py 增 HostSession+create_host_shell(subprocess 管道,Windows=cmd.exe/Linux=bash,批量输出/写探测/kill 同语义,resize no-op;read(4096) 凑满阻塞坑→read1);② main.py exec 哨兵 __host__ 分流;③ runners.py 空串分支降级建 host 会话(键缺失仍 6003 版本过旧;shell 名按 machine_info.os;审计 session_kind=runner_host);④ 验证:runner 单测 6/6(真进程 echo/stdin/kill)+ 后端 r26 11/11 + 触碰面 47 绿(R31 并行会话 10 failed 系其自身缺陷,登记 BUG-044 未代修);⑤ 真机:后端重启 + **reset-token 路由实证修复**(并行会话碰撞把装饰器吞进注释致 404,已拆行)→ 新 token 重拉 runner-local → shell-sessions **code=0** → 测试会话已关。**顺带确认 BUG-042 生效**:用户已成功删除 88b6cb82。Windows 管道模式无 pty(resize/真 TTY 降级)留痕 | rd-fix 第 20 轮收敛 |
| 2026-09-24 | **rd-fix 第 22 轮:新增 R16.F4 修复 BUG-045 机器信息增强**(用户指令:「修复下机器信息,目前内存是0,还可以获取多点信息么」)。根因实锤:`runner/main.py` collect_machine_info 内存采集用 `os.sysconf(SC_PAGE_SIZE/SC_PHYS_PAGES)`(仅 Unix),Windows 必 AttributeError 被吞 → mem_total_gb 恒 0。修复:Windows 分支改 `ctypes GlobalMemoryStatusEx`;按用户指令扩充 os_version/hostname/ip(UDP connect 探出口,不发包)/disk_total_gb/disk_free_gb/cpu_model,逐字段容错(失败整键缺席,不阻塞注册);前端 RunnerMachineInfo 类型扩充 + formatMachine 两行展示(缺字段降级);**后端零改动**。验证:runner pytest 4 新增全绿 + 全量 31/31、tsc 0 错、真机重启 runner 后 DB 全字段落库(mem 31.8GB/ip/hostname/disk/cpu_model)。**并行共存留痕**:与 R31/R31.F1 会话同文件并行(函数面零重叠,双方测试互不破坏);另发现两会话 BUG-043 撞号(本会话第 20 轮「功能已存在核实」vs 对面 R31.F1「本机终端」),BUGS.md 584 行已加让渡标注 | 用户指令(rd-fix 第 22 轮) |
| 2026-09-24 | **rd-fix 第 23 轮:新增 R9.F2 修复 BUG-046 + BUG-UI-070**(用户报障:新建终端 websocket 报错+xterm RenderService.ts:52 dimensions undefined;用户指令:终端滚动条美化)。根因:Terminal.tsx 初始 fit 单 rAF 无守卫 + ResizeObserver 首帧无条件 fit,Runner 终端 Dialog 150ms 动画期容器尺寸未稳 → fit 撞渲染器未就绪崩溃(R31.F1 宿主 shell 落地后会话首次真开,前端时序缺陷首次暴露;ws 报错为连带症状)。修复:safeFit 统一守卫(双 rAF/尺寸>0/disposed/try-catch),工作台与 Runner Dialog 两入口同受益;滚动条 globals.css 纯追加 .xterm-viewport 细条半透明白(终端恒深底,双主题通用) | 用户报障+指令(rd-fix 第 23 轮) |
| 2026-09-24 | **rd-fix 第 24 轮:新增 R26.F2 修复 BUG-047 + R9.F2 收敛**(用户指令:「该 Runner 已有终端会话,请先关闭 提供强制关闭再新建功能」)。BUG-047:后端 shell-sessions 加 `?force=true`——6002 判定处 force 时遍历活跃会话复用 terminal.py 关闭语义(terminal_close kill pty + closed_at)后放行,无 force 零变化;前端 6002 错误分支渲染「强制关闭并新建」按钮。验证:tdd Red→Green、test_r26_runner_shell **12/12**;真机 API 三步链(建 A→无 force 6002→force 0)+ runner 日志「已关闭 A→已创建 NEW」+ DB 新旧会话状态全实证。R9.F2 收敛:BUG-046 残余报错定位为 StrictMode 开发期双挂载伪影,open 延迟双 rAF 根除;BUG-UI-070 verified 迁移;浏览器零错终验因两会话超管互踢(D17)归用户一瞥。**越界发现移交 R31.F1 会话**:Windows cmd.exe 管道模式宿主会话浏览器端零输出(数据面,R31.F1「无 pty」留痕范围) | 用户指令(rd-fix 第 24 轮) |
| 2026-09-24 | **rd-fix 第 25 轮:新增 R31.F2 修复 BUG-048 宿主终端 WS 零输出**(用户报障:「runner 新建的终端没有建立 session,ws://… 没有响应」——即第 24 轮移交的数据面问题,本会话接手)。双层根因均 Windows 管道模式专属:① 默认命令 `["cmd.exe"]` 缺 `/K`,cmd 检测到管道 stdin 进入非交互模式执行完即退 → 读循环 13s EOF「宿主 shell 读取结束」→ 永久静默;② xterm Enter 发裸 `\r`,管道 cmd 只认 `\r\n`(探针实证:\r 零输出 /\r\n 立即执行)——真实 pty 会做的行尾仿真在管道模式缺失。修复:默认命令加 /K + `write_input` 宿主分支写入前归一 `\r→\r\n`(幂等);容器内 pty 会话与后端/前端零改动。验证:runner 35/35(新增存活回归门 test_host_shell_alive_after_spawn);真机 E2E PASS——R31 重启 rd23-term 载新代码 → force 清场建会话(实战复验 BUG-047)→ 裸 WS 探针以**与 xterm Enter 一致的裸 \r** 收到完整回路(提示符→echo 执行→输出→新提示符);探针脚本 `.scratch/rd25_ws_probe.py`。BUG-048 verified 迁移 ISSUES.md | 用户报障(rd-fix 第 25 轮) |
| 2026-09-24 | **rd-fix 第 26 轮:R31.F3 需求修正(BUG-049)+ R26.F3(BUG-050)**(用户指令:「错了,我说的本机是要在本机上直接运行 docker 容器,不用再复制命令」——推翻 R31 Q51 负向规格)。**BUG-049 容器形态**:spawn_local 重写为 `docker run -d`(镜像缺失自动构建,Dockerfile 参数化 BASE_IMAGE、Docker Hub 不可达时自动回退本地 python:3.10[实测 docker.io 直连超时];挂载 docker.sock/env 四键/host.docker.internal 回连);容器名确定性推出(平台重启凭名可停);删除链路补 remove_local_container;exec 消息 cwd=/app 适配(runner 容器 WORKDIR,任务终端默认不变);子进程形态废弃保留存量兼容。**BUG-050**:`_read_loop` 硬编码 .recv 对 docker SDK 标准 SocketIO(只有 .read)秒崩——探测式读法。验证:后端 51/51 + runner 36/36(新增 SocketIO 回归);真机全链:首建 145s(自动构建)→ 容器 online → self_container_id=容器 id → R26 终端真 pty 回路 PASS(root@…:/app# echo 实证);顺带实战复验 BUG-047 force。**留痕**:镜像刷新需手动重建(源码 hash 自动重建归 V2);PRD R31 负向规格推翻待文档同步;存量子进程 runner(rd23-term/local-43f68f17)可经 UI 删除 | 用户指令(rd-fix 第 26 轮) |
| 2026-09-25 | **rd-fix 第 27 轮:新增 R14.F1/R28.F2/R19.F6 修复走查批次 3 open bug**(BUG-UI-071 归档 500 stray import + 导览链式请求治理 / BUG-UI-072 超管头像 404 失效引用清理+前端失败记忆 / BUG-UI-073 审计详情列断词 nowrap)。根因均为 2026-09-24 走查批次一手实证(knowledge.py:31 traceback 等),免分析轮直入分片。**参数分流**:用户随轮附带「创建需求默认分支改 feat/{需求简称首拼≤8字母}_{日期}」——与 PRD 分支模型 `req-{reqId}`(PRD L44/L72-74/L184/L209)显式冲突,属规格变更不进修复循环,分流 /rd-plan 增量(R3 面改造;需求表现无简称字段,首拼派生口径/日期格式/同名冲突后缀待 rd-plan 拍板);BUG-034 维持 open 等用户启动本地 LLM 代理(0.0.0.0:18765)后回归 | 走查批次遗留+用户参数(rd-fix 第 27 轮) |
| 2026-09-25 | **rd-fix 第 27 轮收敛:R14.F1/R28.F2/R19.F6 完成,BUG-UI-071/072/073 verified 迁移 ISSUES.md**。后端:Red 2/2 实锤 ImportError→Green+触碰面 21/21 两轮;真机重启(2905→10750)archive 200/404,主会话独立登录复放同结果;数据:超管 avatar 两列置 NULL(dev 库 aicoding,读回断言,只动该行)。前端:useTourSteps 四查询 enabled 门+TourDialog open prop、utils/avatar.ts failedAvatarUrls 三消费点、审计列 nowrap+col 110;tsc/build 0 错。**越界定性留痕**:全量 pytest 异常=①并行会话同库死锁伪影(无并发复跑 r26/r27 绿)+②test_terminal_api 跨文件隔离缺陷(单跑 8/8 绿,尾随他文件 9 errors,测试基建待办未代修)+③test_r31_local_runner 4F=docker SDK 缺席——按用户口径「docker 本机不装,保证代码 ok」,曾装 7.2.0 已卸回、pyproject 声明已撤销,R31 本机快速创建本机不可用为明示约束。浏览器视觉/network 复核归 rd-test | rd-fix 第 27 轮收敛 |
| 2026-09-25 | **R27 判据 5 真机复现通过,转 ✅(rd-dev;增量3 收官 5/5)**。用户已重录 gitlab_bot_token(2001 短路解除);QA subagent 按分片口径三场景:A sjzs.git manual 绑定 code 0 创建成功(gitlab_repo_id=662)、B 乱编仓库 2011 文案逐字一致、C 以 bot 非成员公共仓库 wangwei/zlj 新构造复现 2013 逐字一致。**决策留痕:2012 不强造**——bot token 有效不可动 + GitLab 对不可见私有库返 404→2011,无真机前提,单测已覆盖,记为接受偏差;测试项目 DELETE 软删清理,基线 0→1→0 零残留。代码零改动;工作区含 rd-fix 第 27 轮未提交改动,待用户按需求点分笔提交 | rd-dev R27 收官 |
| 2026-09-26 | **rd-fix 第 28 轮:新增 R21.F1 修复 BUG-051 工作台门槛口径错位**(用户报障:「工作台的开发任务统计好像不对,核查下看看」)。核查结论:**数字没算错**——summary 与 DB 真值逐项对账一致(created_by=me 口径合规,R21 Q21),用户对比的 8 条 dev 系项目内他人(超管)创建,按规格不计入测试账号卡片(口径歧义非 bug);真缺陷=前端 hasProject 用 owner-only /api/projects(Dashboard.tsx:45-103 / project_service.py:326-331)而数据口径=成员可见(dashboard.py:26-43),非 owner 成员整统计区被空态顶掉。修复:summary 增 visible_projects + 前端门槛同源(分析底稿 .scratch/fix-analysis.md 第 28 轮小节;subagent 误写仓库根 .scratch 已收编)。**口径变更诉求(项目维度统计)归 /rd-plan 拍板,不混本轮**;/api/projects owner-only 遗留归 R2/R12 另轮 | 用户报障(rd-fix 第 28 轮) |
| 2026-09-26 | **rd-fix 第 28 轮收敛:R21.F1 完成,BUG-051 verified 迁移 ISSUES.md**。后端 summary 增 visible_projects(dashboard.py:73 一处);前端门槛 hasProject=(summary?.visible_projects ?? 0)>0 并移除 owner-only useProjectList(Dashboard.tsx:44-46)。验证:Red 2 用例(KeyError)→Green、test_dashboard.py 10/10、tsc 0 错+build 过;真机:测试账号(非 owner 成员)summary visible_projects=1(热加载未重启),主会话独立登录复放一致。**附注定性**:用户对比的 8 条 dev 系超管创建,created_by=me 规格口径下不计入测试账号卡片——非缺陷;项目维度统计口径如需变更走 /rd-plan。代码改动=后端 1 处+前端门槛 2 行+类型 1 行+测试 2 用例,未提交(与第 27 轮累积改动同待用户分笔) | rd-fix 第 28 轮收敛 |
