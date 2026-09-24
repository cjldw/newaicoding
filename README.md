# 旗程 · AI Web 研发流程协作平台

> 一个把「AI 编码助手」组织成团队研发流程的 Web 平台:需求打磨 → 开发/测试/发布任务 → 任务级隔离容器 → Web 终端/实时预览/在线编辑器,全程由 Claude 等大模型驱动,人在平台上解释、打磨、把关。
>
> 参考形态:MonkeyCode(流程) × v0.dev / bolt.new(AI 工作台) × GitHub Codespaces(容器) × rd-flow(需求打磨)。
> 设计基线:**shadcn/ui (New York)** 视觉体系(zinc 色板 / 0.5rem 圆角 / Geist·Inter 字体,见 `design.md`)。

---

## 项目概览

平台把端到端研发闭环沉淀在 Web 上,由 AI 执行、人类把控:

- **流程引擎(M4)**:需求状态机 + 分支自动创建 → 人工智能打磨(R3)→ 统一执行单元按 `dev / test / release` 三种类型拆分(R4-R7),发布自动 merge → 部署 → 网关路由注册;
- **执行环境(M5)**:Runner 在宿主机拉起**任务级隔离容器**(devbox 镜像,内置 Claude CLI / Node / Python / MCP / Skills),提供 **Web 终端**(xterm + pty)、**实时预览**(端口探测 + 网关路由)、**在线编辑器**(GitLab 只读 / 容器读写双模式 + inotify 监听 + Diff,R11);
- **平台底座**:用户账号与三级项目角色(R1/R12/R19)、GitLab 多仓库绑定与自动建仓(R2)、项目级模型接入 + MCP/Skills(R13/R17)、站内信/钉钉通知(R18)、审计与邀请注册(R25/R19)、Dashboard 与四维管理(R21/R22);
- **增量能力(2026-09 下旬)**:平台默认 LLM 回退链(R23)、Runner 外置 shell 与部署角色(R24/R26)、webhook 校验(R25)、用户信息与头像增强(R28)、平台导览与黑白主题(R29/R30,进行中)。

核心流程一句话:**建项目绑仓库 → AI 打磨需求 → 派发 dev 任务进容器干活 → 测试用例评审/测试执行 → 发布 merge 部署 → 网关按域名路由到预览**。

## 架构图

```
┌─────────────────────────────  平台(一台机器)  ─────────────────────────────┐
│                                                                            │
│  frontend (Vite6 + React18)          backend (FastAPI + MySQL8)            │
│  :5173 dev  ──/api,/ws 代理──▶    :8000 uvicorn app.main:app              │
│       │                                  │   │  ▲                            │
│       │  build 静态托管                    │   │  │ routes 表                  │
│       ▼                                  ▼   │  ▼                            │
│  gateway 自研反代 (GATEWAY_PORT=80)  ──Host精确匹配──▶ preview/deploy 路由    │
│       │                                                                      │
│       └── 限流 (单host QPS=100) · WS透传(HMR/TTY) · 404/403/502 异常页       │
└───────────────────────────────────────────────────────────────────────────────┘
                          │ WebSocket(register/heartbeat/指令) + Docker 调用
                          ▼
        ┌────────  Runner 机器 (每台可发现/可部署) ────────┐
        │  runner/main.py (WS客户端, 身份=per-runner token) │
        │  └─ 拉起 devbox 容器(任务级隔离)                  │
        │     ├─ 容器内 Claude CLI + MCP + Skills 干活       │
        │     ├─ 5173/8000 端口映射宿主机预览 20000-29999    │
        │     └─ pty 终端 · inotify 文件监听 · 日志回传       │
        └───────────────────────────────────────────────────┘
```

## 子项目索引

| 子项目 | 技术栈 | 端口 / 入口 | 说明 |
|---|---|---|---|
| `backend/` | Python ≥3.10 · FastAPI · SQLAlchemy 2(asyncio) · asyncmy · alembic · pydantic v2 | `:8000` — `uvicorn app.main:app`;`/docs` 自动 API 文档 | 平台主后端:20+ 路由模块、16 张业务表、双层权限 Guard、审计日志、runner WS 服务端 |
| `frontend/` | Vite6 · React18 · TS5.6 · Tailwind3 · zustand5 · react-query5 · react-hook-form/zod · monaco · xterm | dev `:5173`,生产静态托管 + 反代 `/api` `/ws` | 单页应用:37 页面文件 + 自研 shadcn 风格组件(无 Radix,手写);`src/api/client.ts` 原生 fetch 封装 |
| `gateway/` | Python · FastAPI app(复用 `backend/app/core/gateway.py`) | `GATEWAY_PORT=80 python3 main.py` | 自研反向代理,Host 精确匹配、直查 `routes` 表即时生效、WS 透传、单 host 限流 |
| `runner/` | Python · docker SDK · websockets | 容器 `platform/runner:v1` 或裸机 `python3 main.py` | 分布式执行代理:注册/心跳/对账、start/stop 容器指令、容器管理、pty 终端、文件监听 |
| `docker/devbox` | devcontainers/typescript-node + python3 + Claude CLI + 3×MCP + skills | 任务容器镜像 `platform/devbox:v1` | 每个研发任务的隔离工作台(`sleep infinity` 常驻,端口映射宿主机 preview 区间) |
| `docker/runner` | python:3.12-slim | Runner 镜像 `platform/runner:v1` | 薄代理镜像,`pip install docker websockets fastapi uvicorn` |

## 快速开始

### 环境要求

| 组件 | 版本 |
|---|---|
| Python | ≥ 3.10(pyproject 声明;实测 3.10) |
| Node.js | ≥ 18(Vite6 要求) |
| MySQL | 8.0(库 `aicoding`;测试库 `aicoding_test`;连接串走 `DATABASE_URL`) |
| Docker | 需安装(devbox / runner 容器与镜像构建) |
| GitLab | 可选接入(平台 GitLab token 绑定 / 自动建仓) |

> ⚠️ 全平台时区钉死 `GMT+8`(数据库 `init_command SET time_zone='+08:00'`)。

### 1. 后端(backend/)

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

cp .env.example .env       # 填入真实 DATABASE_URL / PLATFORM_SECRET_KEY / JWT_SECRET_KEY
alembic upgrade head       # 迁移数据库(幂等)
uvicorn app.main:app --reload --port 8000
```

- API 文档:`http://localhost:8000/docs`;健康检查:`/health`
- 测试:`pytest`(46 个 test_*.py,含 R23-R28 回归用例)

### 2. 前端(frontend/)

```bash
cd frontend
npm install
npm run dev     # http://localhost:5173(已代理 /api、/ws 到 localhost:8000)
npm run build   # 生产构建 = tsc -b && vite build,产出静态资源 + 反代
```

### 3. 网关(gateway/)

```bash
cd gateway
GATEWAY_PORT=80 python3 main.py   # 复用 backend app 代码(需 PYTHONPATH 含 backend/,80 端口需权限)
```

### 4. Runner(runner/)

```bash
cd runner
pip install -r requirements.txt
export PLATFORM_URL=ws://localhost:8000/ws/runner \
       RUNNER_TOKEN=plt-runner-xxx \     # per-runner 一次性注册 token(身份=token)
       RUNNER_ID=runner-01 \
       RUNNER_ROLE=worker \              # worker | deploy(deploy 需公网 IP,端口 10000-10099)
       RUNNER_HOST=127.0.0.1             # 网关可达地址
python3 main.py
```

### 5. 构建镜像

```bash
docker build -t platform/devbox:v1  -f docker/devbox/Dockerfile   .        # context=仓库根(COPY skills/)
docker build -t platform/runner:v1 -f docker/runner/Dockerfile   runner/
```

## 目录结构

```
.
├── backend/                  # 平台后端(主进程)
│   ├── app/
│   │   ├── api/              # 路由层:auth/users/projects/requirements/tasks/... + admin/(平台设置/用户/Runner/Skills/审计)
│   │   │   ├── runner_ws.py  # Runner 注册与指令 WebSocket(R16)
│   │   │   └── terminal.py   # Web 终端 + WS(R9)
│   │   ├── core/             # 横切:response 统一响应 / auth JWT / encryption AES-GCM / gateway 反代 / security
│   │   ├── models/           # SQLAlchemy ORM(每表一文件,16 张业务表)
│   │   ├── schemas/          # Pydantic 请求/响应
│   │   ├── services/         # 业务逻辑(26 文件,按模块拆分)
│   │   ├── config.py         # pydantic-settings 配置(.env)
│   │   ├── database.py       # 连接池 pool_size=10 + 时区 GMT+8
│   │   └── main.py           # FastAPI 入口(lifespan 挂 Runner 心跳巡检)
│   ├── alembic/              # 数据库迁移(19+ 个 *_r{编号}_*.py)
│   ├── tests/                # pytest 用例
│   ├── pyproject.toml        # 依赖与工具配置
│   └── .env.example
├── frontend/                 # SPA 前端
│   ├── src/
│   │   ├── api/              # 原生 fetch 封装(client.ts) + 各模块 api + useXxx hooks
│   │   ├── components/       # 业务组件 9 + layout(MainLayout/SettingsLayout/Breadcrumb) + ui 12(自研 shadcn 风格)
│   │   ├── hooks/            # useDragSash / useToast
│   │   ├── pages/            # 37 页面(登录/设置/工作台/项目/需求/任务/测试/发布/知识库/通知/四维管理/5×admin)
│   │   ├── stores/           # authStore.ts(JWT 持久化)
│   │   ├── styles/           # globals.css(37KB 唯一样式文件)
│   │   └── router.tsx        # react-router v6 路由表(RequireRole 超管守卫)
│   ├── vite.config.ts        # :5173,/api 与 /ws 代理
│   └── package.json
├── gateway/                  # 网关独立进程入口(R15)
├── runner/                   # 分布式执行代理(R8/R16)
│   ├── main.py               # WS 客户端主循环(注册/心跳/指令/重连)
│   ├── container_manager.py  # Docker 容器管理
│   ├── terminal_manager.py   # pty 终端
│   ├── file_watcher.py       # inotify 文件监听
│   └── tests/
├── docker/
│   ├── devbox/Dockerfile     # 任务容器镜像(内置 Claude CLI/MCP/Skills)
│   └── runner/Dockerfile     # Runner 镜像
├── docs/20260920_ai_web开发平台/   # 迭代全档案:PRD/ARCH/DEPLOY/BUGS/DESIGNLOG/TESTCASE/TESTREPORT
├── knowledge/                # AI 知识库(CODEBASE/API/DATABASE/FRONTEND/DEPLOYMENT + 10 模块说明书)
├── skills/                   # 平台官方 Skills(镜像预装挂点,R17)
├── design.md                 # shadcn/ui(New York)设计 tokens
└── propmt.md                 # Landing Page 生成提示词模板
```

## 开发规范

| 主题 | 说明 |
|---|---|
| AI 协作规范 | 见 `/knowledge/CODEBASE.md`(代码库底账)与各模块说明书 `/knowledge/modules/` |
| 统一响应 | 后端三键 `{code, message, data}`,`code=0` 成功;错误码 4 位数字按域分段(1xxx 认证 / 4xxx 任务 / 19xxx 权限…) |
| 鉴权 | JWT Bearer(access 2h / refresh 7d),`token_version` 失效机制;超管接口 `require_superadmin`(admin/*) |
| 加密 | 敏感字段 AES-256-GCM 加密落库(列含 `_encrypted`);换密钥**必须重启长驻进程**(见 knowledge/secret-key-rotation-pitfall) |
| 时间 | 全平台 **GMT+8 墙钟**,禁止本地时区存储 |
| 数据库 | MySQL8 + SQLAlchemy 2 async;DDL 走 alembic;**全新环境严禁 create_all 与 alembic 混用** |
| 前端 | 无 axios,统一 `fetch` 走 `client.ts`;组件手写 shadcn 风格,**无 Radix 依赖** |
| 提交 | 中文 conventional(如 `:feat:` / `:books:` / `:art:`),每条 commit 携带 `Co-Authored-By` |
| 测试 | 后端 `pytest --asyncio-mode=auto`;Runner `pytest tests/` |

## CI/CD

**当前无 CI/CD 流水线**,发布为手动流程(详见 `docs/20260920_ai_web开发平台/DEPLOY.md`):

1. 生产密钥重生成(`PLATFORM_SECRET_KEY` + `JWT_SECRET_KEY`)
2. `alembic upgrade head` 迁移数据库
3. 后端 `.env` → `uvicorn app.main:app`
4. 前端 `npm run build` → 静态托管 + 反代 `/api` `/ws`
5. 网关 `GATEWAY_PORT=80 python3 gateway/main.py`
6. 构建 devbox / runner 两镜像推仓库
7. 每台 Runner 部署 + DNS 泛域名 `*.{preview|deploy}_base_domain` 指向网关
8. 验证核心链路(建项目→需求→打磨容器→终端→预览→测试→发布→归档)

> 依赖中间件:MySQL(唯一真实依赖);`REDIS_URL` 仅占位未使用。

## 文档

| 文档 | 位置 |
|---|---|
| 产品需求(PRD) | `docs/20260920_ai_web开发平台/PRD.md`(R1-R30,含增量 3/4) |
| 架构设计决策(D1-D20) | `docs/20260920_ai_web开发平台/ARCH.md` |
| 发布变更清单 + 上线检查单 | `docs/20260920_ai_web开发平台/DEPLOY.md` |
| 缺陷档案 + 修复轮次 | `docs/20260920_ai_web开发平台/BUGS.md` · `ISSUES.md` · `DESIGNLOG.md` |
| 测试用例与报告 | `docs/20260920_ai_web开发平台/TESTCASE.md` · `TESTREPORT.md` |
| 需求主台账 | `knowledge/REQUIREMENTS.md`(模块 M1-M10) |
| 代码库 / 接口 / 数据库 / 前端 / 部署底账 | `knowledge/CODEBASE.md` · `API.md` · `DATABASE.md` · `FRONTEND.md` · `DEPLOYMENT.md` |
| 模块说明书(10 份) | `knowledge/modules/` |
| 主题知识(密钥轮换坑 / 时区约定) | `knowledge/secret-key-rotation-pitfall.md` · `timezone-gmt8-convention.md` |

---

> 仓库: `github.com/cjldw/newaicoding` · 迭代:`backend + frontend + gateway + runner` 四组件独立演进、可单独回滚。
