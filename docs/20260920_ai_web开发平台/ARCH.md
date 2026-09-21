# 架构设计:AI Web 开发平台

> PRD:./PRD.md
> 创建日期:2026-09-20
> 状态:**已确认**

## 现状地图

### 涉及的既有模块

**无业务代码(绿地)**——仓库 `E:\codelab\zhanqiNet\monorepo\newaicoding` 根仅有 `design.md`、`propmt.md` 与 `docs/`。无历史代码/模块需要改动。

### 可复用资产

- `design.md`:**shadcn/ui (New York)** 视觉体系 tokens(zinc 色板 / 0.5rem 圆角 / Geist·Inter 字体 / Tailwind v4 @theme)——D8 前端选型的既有约束与设计基线
- `propmt.md`:Landing Page 生成提示词模板(非架构输入)

### 冲突点

- **D20(新增)与 PRD R15/R16、ARCH D6/D13/D14 冲突**:容器端口已映射宿主机随机端口并回报平台,"Runner 本地代理"层属冗余转发一跳,建议取消(待用户拍板,见 D20)
- 无代码层冲突

### 底账

**无**——`knowledge/` 目录不存在(预期,全新项目)。建议 rd-dev 首期落地后跑 `/rd-knowledge` 建账。

## 决策点清单

### D1:后端语言与框架

- **类别**:集成依赖(决定 SDK 生态)
- **候选方案**:
  | 方案 | 一句话 | 优点 | 缺点 |
  |---|---|---|---|
  | **A Python + FastAPI** | 后端用 FastAPI + asyncio + SQLAlchemy + Celery | 与 Claude Agent SDK Python 版完美契合;AI/数据处理生态最强;Docker SDK 成熟;PRD 已明确"python+react" | WebSocket 高并发需 uvicorn+workers;异步生态稍嫩于 Node |
  | B Node.js + NestJS | 后端用 NestJS + TypeORM + Bull | 与 Claude Agent SDK Node 版契合;WebSocket/SSE 生态最成熟;前端同语言 | AI 生态弱于 Python;Docker SDK 稍次 |
  | C Go + Gin | 后端用 Gin + GORM + Asynq | 性能最强;并发最好;Docker 原生(Docker 就是 Go 写的) | Claude Agent SDK 无官方 Go 版,需手写 HTTP 客户端;AI 生态最弱;开发效率最低 |
- **推荐**:**方案 A(Python + FastAPI)**——PRD 已明确"python+react",且 Claude Agent SDK Python 版是官方一等公民,AI 工作流生态(LangChain/LlamaIndex 等)最丰富,便于后续扩展;FastAPI 自带 OpenAPI 文档、asyncio 原生支持 WebSocket/SSE,与 Docker SDK for Python 配合顺畅
- **影响的需求点**:全部(地基)
- **冲突点**:无
- **状态**:✅ 已确认(自动确认,依据:PRD 明确技术栈;Claude SDK 官方 Python 版;FastAPI 生态成熟)

### D2:数据库与 ORM

- **类别**:数据模型
- **候选方案**:
  | 方案 | 一句话 | 优点 | 缺点 |
  |---|---|---|---|
  | **A MySQL 8.0 + SQLAlchemy 2.0 + asyncmy** | 主库 MySQL 8,异步驱动 asyncmy | 用户点名;团队熟悉度高;运维工具成熟;asyncmy 是 PyMySQL 的 asyncio 版,性能优于 aiomysql | JSON 不如 PG;异步生态稍弱;需自己处理半结构化字段 |
  | B MySQL 8.0 + SQLAlchemy 2.0 + aiomysql | 主库 MySQL 8,异步驱动 aiomysql | 同上 | aiomysql 已停止维护,不推荐 |
  | C PostgreSQL 16 + SQLAlchemy 2.0 async | 主库 PG,ORM 用 SQLAlchemy 2.0 async | JSONB 强;行级锁;pgvector 预留向量检索 | 用户已明确要 MySQL |
- **推荐**:**方案 A(MySQL 8.0 + SQLAlchemy 2.0 + asyncmy)**——用户点名 MySQL;asyncmy 是目前 MySQL 异步驱动中最活跃的;JSON 字段用 MySQL 8 的 `JSON` 类型(支持 JSON 查询,够用)
- **关键调整**:
  - 半结构化字段(tool_calls/test_cases/ai_breakdown/extended_attributes)用 `JSON` 类型
  - 行级锁:`SELECT ... FOR UPDATE`(MySQL InnoDB 支持)
  - 事件总线:不用 PG `LISTEN/NOTIFY`,改用**应用内 asyncio.Queue + WebSocket 推送**(单实例够用)
  - 知识库向量检索(R14):MySQL 8.0 不支持向量,**V1 只用 FULLTEXT 全文索引**,V2 再考虑引入向量库(如 Milvus/Qdrant)
- **影响的需求点**:全部数据持久化
- **冲突点**:无
- **状态**:✅ 已确认(用户点名 MySQL)

### D3:Claude Agent SDK 与 AI 集成模式

- **类别**:集成依赖
- **候选方案**:
  | 方案 | 一句话 | 优点 | 缺点 |
  |---|---|---|---|
  | **A `claude-agent-sdk` Python 版 + 容器内 Claude CLI 并存** | 平台后端用 Python SDK 跑主路径(任务执行);容器内装 Claude CLI 作为用户介入入口(R9) | 与 D1 一致;SDK 可控(结构化事件流/工具调用拦截/审计);CLI 给用户"手动介入"的逃生通道 | 两套集成点,需要同步状态(SDK 会话 vs CLI 会话) |
  | B 仅 SDK,容器内不装 CLI | 只走 SDK | 简单 | 用户无法在终端手动跑 claude,R9 双通道变单通道 |
  | C 仅 CLI,SDK 不用 | 平台通过 pty 接管 CLI 输入输出 | 简单 | 无法结构化解析工具调用事件,活动流做不到 |
- **推荐**:**方案 A(SDK 主路径 + CLI 兜底)**——PRD R9 已确认"SDK 主 + CLI 辅";Python SDK 提供 `ClaudeSDKClient` + `query()` 异步迭代器,工具调用事件结构化,便于推送到前端活动流;容器内 CLI 由用户手动启动,与 SDK 会话相互独立(PRD R9 已明确)
- **影响的需求点**:R3、R4、R5、R6、R7、R9、R14
- **冲突点**:无
- **状态**:✅ 已确认(用户确认)

### D4:GitLab 集成模式

- **类别**:集成依赖
- **候选方案**:
  | 方案 | 一句话 | 优点 | 缺点 |
  |---|---|---|---|
  | **A `python-gitlab` 库 + 个人 token 走 HTTPS clone** | API 调用用 python-gitlab(bot + 用户 token);Git 操作用 `git clone https://oauth2:{token}@gitlab/...` | python-gitlab 是官方推荐;HTTPS clone 比 SSH 简单(容器内不用配 key);token 直接放 URL | token 会出现在 git remote 配置里(需清理) |
  | B `pygit2` 操作 Git | 不依赖系统 git 命令 | 可编程性强 | 生态小;复杂操作(rebase/merge)不如原生 git |
  | C 直接调 GitLab REST API + 系统 git 命令 | 不用 python-gitlab | 依赖最少 | python-gitlab 已封装好分页/重试/错误处理,自己写浪费 |
- **推荐**:**方案 A(python-gitlab + HTTPS clone)**——python-gitlab 是 GitLab 官方推荐的 Python 客户端,覆盖所有 API(项目/分支/MR/webhook/成员);容器内 git 操作用 HTTPS + token 是最简单的(不需要配 SSH key);token 安全通过 `git config --global credential.helper` 或环境变量注入(容器销毁即失效)
- **影响的需求点**:R2、R3、R4、R5、R6、R7、R11
- **冲突点**:无
- **状态**:✅ 已确认(自动确认,依据:python-gitlab 官方推荐;HTTPS clone 最简单;token 环境变量注入)

### D5:实时通道统一方案

- **类别**:集成依赖 + 性能
- **候选方案**:
  | 方案 | 一句话 | 优点 | 缺点 |
  |---|---|---|---|
  | **A 单一 WebSocket 网关 + 频道复用** | 所有实时流量(终端 TTY、AI 事件流、文件 watcher、预览 HMR 转发、协同通知)走同一个 WebSocket 连接,用频道(channel)区分 | 连接数少;鉴权统一;前端只需维护一个 ws | 单连接故障影响所有功能;消息协议需自己定义 |
  | B 多种协议分离 | 终端走 WebSocket;AI 事件走 SSE;HMR 走容器原生 ws;文件 watcher 走轮询 | 每通道用最适合的协议 | 前端要维护多个连接;鉴权分散;HMR 必须穿透 |
  | C Socket.IO | 用 Socket.IO 统一 | 自带房间/重连/降级 | 引入额外依赖;协议非标准 ws |
- **推荐**:**方案 A(单一 WebSocket 网关 + 频道)**——FastAPI 的 `websockets` 库原生支持;网关层做鉴权(JWT)+ 路由(按 channel 分发到 Redis pub/sub 或直接到容器 docker exec);HMR 是容器内的 ws,需要网关做 ws 代理(透传)
- **影响的需求点**:R9、R10、R11、R4(活动流)
- **冲突点**:无
- **状态**:✅ 已确认(自动确认,依据:FastAPI 原生支持;连接数少;鉴权统一)

### D6:容器编排与生命周期(Runner 架构)

- **类别**:集成依赖 + 一致性
- **候选方案**:
  | 方案 | 一句话 | 优点 | 缺点 |
  |---|---|---|---|
  | A 单机 Docker + Docker SDK for Python | 直接调宿主机 Docker socket(/var/run/docker.sock),Python SDK 管理容器 | 最简单 | 单机瓶颈;无法扩展到多机;用户明确要求 Runner 架构 |
  | **B Runner 架构(类似 GitLab Runner)** | 平台后端不直接调 Docker;**Runner 作为代理节点**部署在不同机器上,主动 WebSocket 连接平台,接收任务指令,本地调 Docker SDK 管理容器 | 容器可在不同机器上跑;水平扩展;Runner 在内网/NAT 后也能用(主动连接);与 GitLab Runner 模式一致,业界验证 | 架构复杂度增加;需要 Runner 进程 + Runner 上的本地代理;WebSocket 流量路由需要经过 Runner |
  | C Kubernetes + client-python | 平台跑在 K8s 里,用 K8s API 管理 Pod | 多机扩展;资源隔离好 | 运维成本高;Runner 架构更轻量 |
- **推荐**:**方案 B(Runner 架构)**——用户明确要求;Runner 模式是 GitLab Runner / GitHub Actions Runner 验证过的成熟模式;Runner 主动连接平台(WebSocket)使得 Runner 在内网也能用;平台后端只负责调度与状态机,容器管理下发到 Runner
- **Runner 职责**(薄代理):
  - 接收平台的"启动容器"指令(镜像 + env + 资源限制 + 端口映射)
  - 本地 `docker run`(通过 Docker SDK)
  - 监听本地容器事件(start/die/OOM),实时回传平台
  - 接收"停止/销毁/exec"指令并执行
  - 心跳保活(30s)
- **平台后端职责**:
  - Runner 注册/心跳/状态管理
  - 任务调度(最少负载 + role 匹配)
  - 状态机(MySQL 行级锁)
  - WebSocket 网关(把终端/预览/文件 watcher 流量转发到 Runner)
- **端口直连(D20 修订,原"本地代理"已取消)**:
  - Runner 启动容器时分配随机宿主机端口(范围 20000-29999)**直接回报平台**
  - 平台网关 upstream 直连 `http://{runner_host}:{mapped_port}` 到容器,无中间代理层
- **影响的需求点**:R4、R8、R9、R10、R15、R16
- **冲突点**:无
- **状态**:✅ 已确认(用户明确要求 Runner 架构)

### D7:任务调度与并发控制

- **类别**:一致性并发
- **候选方案**:
  | 方案 | 一句话 | 优点 | 缺点 |
  |---|---|---|---|
  | **A MySQL 行级锁 + asyncio 任务队列** | 任务状态机用 MySQL `SELECT ... FOR UPDATE`;任务执行用 asyncio.Queue + worker 协程;并发配额用 MySQL 计数器 | 无外部依赖(与 D2 一致);事务一致性好;异步高效 | 单点(V1 接受) |
  | B Celery + Redis | 任务队列用 Celery | 生态成熟;分布式 | 引入 Redis 依赖;V1 单实例过度 |
  | C ARQ(Redis 异步队列) | 轻量 asyncio 队列 | 简单 | 仍需 Redis |
- **推荐**:**方案 A(MySQL 行级锁 + asyncio)**——V1 单实例;与 D2 MySQL 选型一致;任务状态机(pending → running → done/failed)用 MySQL 事务保证原子性;Git 冲突策略(PRD 已定:乐观并行 + AI rebase)由 AI 在容器内执行,平台层只需保证任务超时强制 push
- **影响的需求点**:R4、R5、R6、R7
- **冲突点**:无
- **状态**:✅ 已确认(自动确认,依据:与 D2 一致;单实例够用;MySQL 事务保证状态机原子性)

### D8:前端技术栈

- **类别**:前端架构
- **候选方案**:
  | 方案 | 一句话 | 优点 | 缺点 |
  |---|---|---|---|
  | **A React 18 + Vite + TypeScript + Tailwind + shadcn/ui + Zustand + react-query** | 现代化主流栈 | 生态最成熟;Monaco/xterm.js 都有 React 封装;shadcn/ui 组件质量高;Zustand 轻量;react-query 处理服务端状态 | 学习曲线对新手稍陡 |
  | B Vue 3 + Vite + Element Plus | 国内生态友好 | 中文文档全 | Monaco/xterm 封装不如 React 生态 |
  | C Next.js 14 (App Router) | 全栈框架 | SSR/SSG | 本平台是内部工作台,不需要 SEO/SSR;Next.js 对 WebSocket/长连接不友好 |
- **推荐**:**方案 A(React 18 + Vite + TS + Tailwind + shadcn/ui + Zustand + react-query)**——PRD 已明确"react";Monaco(`@monaco-editor/react`)、xterm.js(`xterm-for-react`)都有成熟 React 封装;shadcn/ui 提供高质量组件(Table/Form/Dialog/Tabs),与 Tailwind 配合快速搭建工作台布局;Zustand 管理本地状态(编辑器打开的文件/终端 Tab),react-query 管理服务端状态(项目/需求/任务列表)
- **影响的需求点**:全部前端页面
- **冲突点**:无
- **状态**:✅ 已确认(自动确认,依据:PRD 明确 react;Monaco/xterm React 封装成熟;shadcn/ui 组件质量高)

### D9:加密与密钥管理

- **类别**:安全权限
- **候选方案**:
  | 方案 | 一句话 | 优点 | 缺点 |
  |---|---|---|---|
  | **A AES-256-GCM + 单平台密钥(环境变量)** | 所有敏感字段(GitLab token / LLM api_key)用 AES-256-GCM 加密,密钥从环境变量 `PLATFORM_SECRET_KEY` 读 | 最简单;V1 单实例够用 | 密钥泄露需全量重加密 |
  | B HashiCorp Vault | 外部密钥管理 | 企业级 | V1 过度 |
  | C AWS KMS / 云 KMS | 云托管 | 安全 | 依赖云服务,不符合私有化部署 |
- **推荐**:**方案 A(AES-256-GCM + 环境变量)**——V1 私有化部署,环境变量是最常见的方式;Python 用 `cryptography` 库;密钥轮换通过"双密钥过渡期"实现(`PLATFORM_SECRET_KEY` + `PLATFORM_SECRET_KEY_OLD`,解密时先试新钥再试旧钥)
- **影响的需求点**:R1、R2、R13
- **冲突点**:无
- **状态**:✅ 已确认(自动确认,依据:V1 私有化部署;cryptography 库成熟;双密钥过渡期支持轮换)

### D10:容器镜像 `platform/devbox:v1` 依赖清单

- **类别**:集成依赖(Q1 留给 rd-arch)
- **候选方案**:
  | 方案 | 一句话 | 优点 | 缺点 |
  |---|---|---|---|
  | A Ubuntu 24.04 + 多阶段构建 | 基于 ubuntu:24.04,装 Python 3.12/Node 22/git/Claude CLI/常用工具 | 镜像可控;工具链新 | 镜像体积大(~2GB);需自己维护基础工具链 |
  | **B 基于 `mcr.microsoft.com/devcontainer/universal:linux` 加装 Claude CLI** | 用微软官方开发容器镜像作基础,再装 Claude CLI | 预装 Python/Node/Go/Rust/git/docker CLI 等主流工具链;微软官方维护;省去自装麻烦 | 镜像体积大(~3GB);包含一些用不到的工具 |
  | C 多镜像(前端/后端分开) | 前端 node:22,后端 python:3.12 | 体积小 | 任务可能需要同时跑前后端,多容器复杂 |
- **推荐**:**方案 B(基于 `mcr.microsoft.com/devcontainer/universal:linux` 加装 Claude CLI)**——devcontainer/universal 是微软官方维护的开发容器,预装 Python/Node/Go/Rust/git/docker CLI 等主流工具链,省去自装麻烦;只需在其基础上 `npm install -g @anthropic-ai/claude-code` 即可;体积大但 V1 单机存储够用
- **镜像 Dockerfile**:
  ```dockerfile
  FROM mcr.microsoft.com/devcontainer/universal:linux

  # 切换到 root 安装 Claude CLI
  USER root

  # Claude CLI(通过 npm)
  RUN npm install -g @anthropic-ai/claude-code

  # 预装高频 Python 包(加速任务启动)
  RUN pip3 install --break-system-packages \
      fastapi uvicorn sqlalchemy pytest requests httpx

  # 预装高频 npm 包
  RUN npm install -g vite create-react-app

  # 切回 codespace 用户
  USER codespace

  WORKDIR /workspace
  CMD ["/bin/bash"]
  ```
- **任务创建时的环境变量注入**(任务级,容器销毁即失效):
  | 环境变量 | 值 | 用途 |
  |---|---|---|
  | `LLM_BASE_URL` | 项目模型配置的 `base_url` | 通用 LLM endpoint |
  | `LLM_API_KEY` | 项目模型配置的 `api_key`(解密后) | 通用 LLM key |
  | `LLM_MODEL` | 项目模型配置的 `model` | 模型名 |
  | `ANTHROPIC_BASE_URL` | 同 `LLM_BASE_URL` | Claude CLI 兼容 |
  | `ANTHROPIC_API_KEY` | 同 `LLM_API_KEY` | Claude CLI 兼容 |
  | `GITLAB_TOKEN` | 创建任务的用户个人 GitLab token(解密后) | git clone/push/pull |
  | `GITLAB_INSTANCE_URL` | GitLab 实例 URL(平台设置) | git remote |
  | `GIT_USER_NAME` | 用户 GitLab username | git commit author |
  | `GIT_USER_EMAIL` | 用户 GitLab email | git commit author |
  | `TASK_ID` / `PROJECT_ID` / `REQ_ID` | 任务/项目/需求 id | 任务上下文 |
- **git credential.helper 配置**(容器启动脚本):
  ```bash
  git config --global credential.helper '!f() { echo "username=oauth2"; echo "password=${GITLAB_TOKEN}"; }; f'
  git config --global user.name "${GIT_USER_NAME}"
  git config --global user.email "${GIT_USER_EMAIL}"
  ```
  后续 `git clone https://gitlab.example.com/...` / `git push` 自动用 token,无需手动带
- **安全边界**:
  - token **仅注入到容器 env**,不落盘到镜像/日志/ volumes
  - 容器销毁即失效(任务级容器,任务结束即销毁)
  - 容器内进程的 env 可通过 `/proc/{pid}/environ` 读到,**V1 不做额外防护**(容器网络隔离 + 出网白名单 + 任务级短生命周期)
  - 创建任务前平台**先校验**用户 token 对所需 repo 有 read+write 权限(调 GitLab API),校验通过才注入
- **影响的需求点**:R8
- **冲突点**:无
- **状态**:✅ 已确认(用户指定基于 devcontainer/universal)

### D12:任务对话框文件上传与 `@文件` 引用

- **类别**:集成依赖(任务与文件系统交互)
- **候选方案**:
  | 方案 | 一句话 | 优点 | 缺点 |
  |---|---|---|---|
  | **A 平台中转:前端 → 平台 → Runner → 容器 `/tmp/uploads/`** | 前端上传到平台,平台通过 Runner WebSocket 通道转发到容器 | 平台可控(权限/大小限制/审计);文件元数据存 MySQL | 大文件占用平台带宽 |
  | B 前端直传容器(平台返回预签名 URL) | 平台生成容器内文件上传 URL,前端直传 | 平台带宽小 | 容器在内网,前端无法直连;需要额外的文件服务 |
  | C 上传到平台对象存储(MinIO),容器内挂载 | 文件存 MinIO,容器启动时挂载 | 文件持久化;容器销毁不丢 | 引入 MinIO 依赖;容器挂载复杂;用户说"容器销毁文件丢失可接受" |
- **推荐**:**方案 A(平台中转)**——简单直接;V1 单文件 ≤ 50MB,平台带宽够用;文件元数据(文件名/大小/上传人)存 MySQL,便于审计;容器销毁文件丢失符合"临时文件"定位
- **`@文件` 引用实现**:
  - 前端在对话框输入 `@` 时,调 `GET /api/tasks/{tid}/files/uploads` 获取当前任务已上传文件列表,自动补全
  - 用户选中后插入 `@filename`;发送时,平台后端解析 `@filename` → 查 `task_uploaded_files` 表 → **< 100KB 文件:读取内容注入 prompt**(格式:`\n\n---\nFile: {filename}\n```\n{content}\n```\n---\n`);**≥ 100KB 文件:只注入路径**(`\n\n---\nFile: {filename} (size: {size} bytes)\nPath: {container_path}\n---\n`,AI 用 read_file 工具自己读)
  - `file_refs` 字段记录引用关系(JSONB),便于审计
- **影响的需求点**:R4
- **冲突点**:无
- **状态**:✅ 已确认(用户确认)

### D13:Runner 通信协议与注册

- **类别**:集成依赖(Runner 架构基础)
- **候选方案**:
  | 方案 | 一句话 | 优点 | 缺点 |
  |---|---|---|---|
  | A HTTP 长轮询 | Runner 定期 `GET /api/runner/jobs`,平台返回任务 | 简单 | 实时性差;HTTP 开销大 |
  | **B WebSocket** | Runner 与平台保持长连接,平台推送任务指令 | 实时性好;与 D5 统一网关一致;心跳保活简单 | 需要处理断线重连 |
  | C gRPC | 双向流 | 性能最强 | 引入 gRPC 依赖;V1 过度 |
- **推荐**:**方案 B(WebSocket)**——与 D5 统一网关一致;实时性好(平台可主动推送任务指令给 Runner);心跳保活简单(WebSocket ping/pong);断线重连由 Runner 客户端实现
- **Runner 注册流程**:
  1. 超管在"平台设置 → Runner 管理"页生成 Runner token(一次性,仅显示一次)
  2. 运维在 Runner 机器上 `docker run -e PLATFORM_URL=wss://platform.example.com/ws/runner -e RUNNER_TOKEN=xxx platform/runner:v1`
  3. Runner 启动后 WebSocket 连接 `wss://platform.example.com/ws/runner`,发送 `{"type": "register", "token": "xxx", "machine_info": {...}}`
  4. 平台校验 token(bcrypt hash 对比)→ 注册成功,标记 Runner online
  5. Runner 每 30s 发 `{"type": "heartbeat", "timestamp": ...}`,平台 60s 未收到标记 offline
- **WebSocket 消息协议**(JSON):
  - 平台 → Runner:`{"type": "start_container", "task_id": ..., "image": ..., "env": {...}, "ports": [...], ...}` / `{"type": "stop_container", "container_id": ...}` / `{"type": "exec", "container_id": ..., "cmd": ..., "pty": true}`
  - Runner → 平台:`{"type": "container_started", "container_id": ..., "ports": {...}}` / `{"type": "container_event", "event": "die|oom|...", "container_id": ...}` / `{"type": "heartbeat", ...}`
- **安全**:
  - Runner token bcrypt hash 存 MySQL,平台不存明文
  - WebSocket 连接校验 token(register 消息)
  - Runner 时钟漂移校验(heartbeat 带时间戳,平台校验 ±5min)
- **影响的需求点**:R16
- **冲突点**:无
- **状态**:✅ 已确认(用户确认)

### D14:部署任务的 Runner 专用化

- **类别**:一致性并发(部署容器长驻,不能漂移)
- **候选方案**:
  | 方案 | 一句话 | 优点 | 缺点 |
  |---|---|---|---|
  | **A 专用 deploy Runner** | Runner 分 `worker`(跑任务容器,任务结束销毁)和 `deploy`(跑部署容器,长驻);部署任务只调度到 `role=deploy` 的 Runner | 部署容器固定在特定机器,IP/域名稳定;worker Runner 可动态增减 | 需要额外维护 deploy Runner |
  | B 任何 Runner 都可跑部署 | 部署 URL 指向 Runner IP:端口 | 简单 | Runner 动态增减时部署 URL 会变;Runner 掉线部署就挂 |
- **推荐**:**方案 A(专用 deploy Runner)**——部署容器长驻(R7 deployed 后不销毁),需要**固定在特定 Runner 上**(IP 稳定,域名/端口可访问);deploy Runner 是"绑定公网 IP / 域名"的机器,跑部署任务的容器;worker Runner 只跑开发/测试任务(任务结束销毁)
- **部署 URL 路由(D20 修订)**:
  - 部署任务 deployed 后,路由/公网直接指向 `http://{deploy_runner_public_ip}:{deploy_port}`
  - 部署容器启动时将容器 8000 端口**直接映射到宿主机 `{deploy_port}`**(10000-10099),无中间代理层
- **影响的需求点**:R7、R8、R15、R16
- **冲突点**:无
- **状态**:✅ 已确认(用户确认)

### D15:MCP server 与 Skills 集成模式

- **类别**:集成依赖(AI 能力扩展)
- **候选方案**:
  | 方案 | 一句话 | 优点 | 缺点 |
  |---|---|---|---|
  | **A 混合策略:镜像预装 + 项目级配置注入 + Skills 市场** | 常用 MCP server 与 Skills 预装到镜像;项目级 MCP 配置(JSON)与 Skills(.md 文件)注入到容器;平台级 Skills 市场供项目选择安装 | 覆盖 80% 场景;简单直接;与 Claude Code 原生格式一致 | 有状态/资源密集的 MCP server 不适合(V2 再做远程 MCP) |
  | B 全部远程化 | MCP server 跑在平台的长期服务里,任务容器通过 HTTP/SSE 连接 | 真正共享;状态持久 | 架构复杂;V1 过度 |
  | C 仅镜像预装 | 不支持项目级自定义 | 最简单 | 灵活性差 |
- **推荐**:**方案 A(混合策略)**——镜像预装常用 MCP server 与 Skills(无状态/轻量级);项目级配置注入(项目特定/需项目级 token);平台级 Skills 市场(平台官方维护,项目选择安装)
- **MCP server 分类与方案**:
  | 类型 | 方案 | 例子 |
  |---|---|---|
  | 无状态/轻量级 | **镜像预装** | filesystem / git / github / sqlite / brave-search |
  | 项目特定/需项目级 token | **项目级配置注入**(JSON 编辑 + 模板) | 项目内部 API / 项目自己的 PostgreSQL/Redis |
  | 有状态/资源密集/跨任务共享 | **远程 MCP server**(V2) | 知识库查询 / 数据库连接池 |
- **Skills 分类与方案**:
  | 类型 | 方案 | 例子 |
  |---|---|---|
  | 平台官方维护 | **平台级 Skills 市场** | "代码审查" / "写测试" / "重构" |
  | 项目自定义 | **项目级 Skills**(上传 `.md` 文件) | "项目特定的部署流程" |
  | 用户级(跨项目) | **V1 不做** | "个人习惯的提交信息格式" |
- **注入机制**(任务创建时):
  - **MCP server**:平台读 `projects.mcp_config_encrypted` 解密 → 与镜像预装的 `~/.claude/config.json` **合并**(项目级覆盖同名)→ 写入容器
  - **Skills**:平台读 `project_skills` 关联的 Skills 内容 → 写入容器 `~/.claude/skills/{name}.md`(项目级覆盖镜像预装同名)
- **安全**:
  - MCP 配置里的敏感信息(数据库密码/API key)**AES-256-GCM 加密存储**(与 D9 一致)
  - 接口返回时**打码**(前 4 位 + 后 4 位,中间 ***)
  - 容器内 env 注入时解密
- **影响的需求点**:R17
- **冲突点**:无
- **状态**:✅ 已确认(用户确认)

### D16:权限模型落地(R19 双层角色)
- **类别**:安全权限(PRD R19 增量)
- **候选方案**:
  | 方案 | 一句话 | 优点 | 缺点 |
  |---|---|---|---|
  | **A 代码固化 + FastAPI 依赖项双层 Guard** | 平台级 `require_superadmin` 依赖;项目级 `require_project_role(level)` 依赖(**超管=虚拟 owner,R19**);所有项目资源查询统一经"成员项目集合"过滤(超管=全部);审计为声明式依赖 `audit(type)` | 与 R19"矩阵代码固化"一致;越权防护统一在依赖注入层;FastAPI Depends 天然组合 | 权限变更需发版(内部平台可接受) |
  | B Casbin 策略引擎 | 动态权限策略 | 可热更 | 与 R19"不做权限点动态配置"相悖,过度设计 |
- **推荐**:方案 A。前端配套:路由 meta 标注所需角色 + 菜单按角色渲染(R19/R22 导航),后端为唯一事实源
- **影响的需求点**:R12、R19、R20、R22
- **冲突点**:无
- **状态**:✅ 已确认(自动确认,依据:PRD R19 已定"矩阵代码固化")

### D17:JWT 立即失效机制(R19 禁用即全失效)
- **类别**:安全权限(认证会话)
- **候选方案**:
  | 方案 | 一句话 | 优点 | 缺点 |
  |---|---|---|---|
  | **A token_version 机制** | `users.token_version`;登录/禁用/改密时 +1,JWT payload 携带;鉴权依赖每请求点查 users(status + token_version),不匹配即 401 → **禁用即全失效**(Q16) | 严格立即失效;无额外存储;点查代价可忽略 | 每请求一次 DB 点查 |
  | B 黑名单表 | 维护失效 token 名单 | 不查用户表 | 额外存储 + 清理任务 |
  | C 仅靠过期 | 禁用等 access 自然过期 | 最简 | 违反 Q16 已确认决策 |
- **推荐**:方案 A。access 2h + refresh 7d 双 token 均校验 token_version
- **影响的需求点**:R1、R19
- **冲突点**:无
- **状态**:✅ 已确认(自动确认,依据:Q16 已确认"禁用即全失效")

### D18:R20 项目知识库模型与导入
- **类别**:数据模型 / 集成(PRD R20 增量)
- **候选方案**:
  | 方案 | 一句话 | 优点 | 缺点 |
  |---|---|---|---|
  | **A 双表 + 后台导入任务** | `knowledge_bases`(source_type=blank/repo_import + source_config)+ `knowledge_docs`(树形 path);导入/同步为后台任务(D7 asyncio 队列),经 python-gitlab(D4)**bot token** 拉取目录树 .md 生成快照 | 与 R20 已定行为一一对应;导入型只读由后端 guard 强制(source_type 判定) | 无 |
  | B 实时读取不落库 | 查看时实时调 GitLab API | 永远一致 | 不可离线;与 R20"快照+手动同步"已确认决策相悖 |
- **推荐**:方案 A。搜索 V1 用 MySQL FULLTEXT(与 D2 关键调整一致,向量检索 V2)
- **影响的需求点**:R20
- **冲突点**:无
- **状态**:✅ 已确认(自动确认,依据:R20 Q19/Q20 已确认)

### D19:R21/R22 聚合视图与导航
- **类别**:数据模型 / 前端架构(PRD R21/R22 增量)
- **候选方案**:
  | 方案 | 一句话 | 优点 | 缺点 |
  |---|---|---|---|
  | **A 无新表聚合查询 + 前端路由增量** | 四维聚合接口走 SQL IN(成员项目)+ created_by 过滤(R21 口径),无新表;前端新增路由"工作台"与"项目管理"分组(四维子路由),复用既有创建接口做快速创建(project_id 入参 + 前置校验复用) | 零冗余存储;快速创建与项目内入口同源校验 | 聚合查询跨项目 IN 列表(单用户 ≤50 项目,量级可控) |
  | B 读扩散冗余表(用户维度汇总表) | 维护"我的"汇总表 | 查询快 | 数据冗余+一致性维护,V1 过度 |
- **推荐**:方案 A
- **影响的需求点**:R21、R22
- **冲突点**:无
- **状态**:✅ 已确认(自动确认,依据:R21/R22 Q21–Q24 已确认)

### D20:网关链路简化——取消 Runner 本地代理层 ⚠️
- **类别**:集成 / 性能(**与 PRD R15/R16、ARCH D6/D13/D14 冲突**)
- **候选方案**:
  | 方案 | 一句话 | 优点 | 缺点 |
  |---|---|---|---|
  | **A 取消本地代理,网关直连** | 预览 upstream = `http://{runner_host}:{mapped_port}`(Runner 已回报映射);部署容器直接映射宿主机 `{deploy_port}`(10000-10099),公网直连 `http://{deploy_runner_public_ip}:{deploy_port}` | 少一个组件与配置生成/reload;链路短一跳;故障点少 | 失去代理层统一入口(V2 TLS/限流需另做) |
  | B 维持本地代理(现状) | Runner 上 Nginx 转发到容器端口 | 入口统一,未来可在该层加 TLS | 端口已映射宿主机,代理层为纯转发冗余;每 Runner 多维护一套 Nginx |
- **推荐**:方案 A。理由:V1 HTTP only 无 TLS 需求;V2 上 HTTPS 在平台网关前置 Caddy/Nginx 终结即可,无需 Runner 层代理
- **影响的需求点**:R7、R8、R10、R15、R16(采纳则回写 PRD)
- **冲突点**:**与 PRD R15/R16 原文冲突**,需用户拍板
- **状态**:✅ 已确认(用户拍板:取消本地代理,采纳方案 A)

### D11:Web 终端实现方案(Runner 架构下)

- **类别**:集成依赖 + 性能
- **候选方案**:
  | 方案 | 一句话 | 优点 | 缺点 |
  |---|---|---|---|
  | **A xterm.js + FastAPI WebSocket + Runner 代理 + docker exec (pty)** | 前端 xterm.js;后端 FastAPI WebSocket;**Runner 上执行** `docker exec -it` 分配 pty;平台通过 Runner WebSocket 通道转发 | 主流方案(GitHub Codespaces / Gitpod 都这么做);xterm.js 成熟;FastAPI WebSocket 原生支持;Runner 架构下唯一可行方案(平台无法直接访问容器) | 需自己管理 pty 生命周期(僵尸进程/孤儿 shell);链路比单机多一跳 |
  | B xterm.js + ttyd / wetty 中间层 | 容器内跑 ttyd(轻量 WebSocket 终端服务),Runner 做反向代理 | ttyd 是成熟的开源 Web 终端;自带 pty 管理 | 引入额外进程;与 Claude SDK 事件流整合需额外通道 |
  | C xterm.js + gotty | 类似 ttyd,Go 实现 | 性能好 | 不如 ttyd 活跃;同样需要容器内跑额外进程 |
  | D 自研 pty 服务(Go/Rust) + Runner 代理 | 单独写一个高性能 pty 服务,通过 gRPC/Unix Socket 与 Runner 通信 | 性能最强;可定制 | 开发成本高;V1 过度 |
- **推荐**:**方案 A(xterm.js + FastAPI WebSocket + Runner 代理 + docker exec)**——Runner 架构下平台无法直接访问容器,必须通过 Runner 代理;Runner 上的 `docker exec` 与单机模式一致,只是执行者从平台后端变为 Runner
- **链路**:
  ```
  用户浏览器
     ↓ WebSocket(/ws/terminal/{session_id})
  平台网关(FastAPI,鉴权 + 频道路由)
     ↓ WebSocket(/ws/runner,平台 ↔ Runner 已有通道)
  Runner(接收终端指令,本地 docker exec)
     ↓ Docker SDK(exec_create + exec_start,tty=True)
  容器(/workspace 下的 bash)
  ```
- **关键实现要点**(保证终端效果):
  1. **xterm.js 本地回显**:用户输入立即在前端显示,不等服务器回显;服务器回显作为"权威回显"覆盖本地回显——**用户感觉不到延迟**(xterm.js 默认行为)
  2. **pty 会话复用**:Runner 维护 `session_id → docker exec pid` 映射表;WebSocket 断线重连时前端带 `session_id`,Runner **attach 而非新建** pty——**shell 历史/工作状态不丢**
  3. **Runner 本地缓冲 + 批量推送**:高频输出时(AI 跑 `npm install` / `pytest`),Runner 每 50ms 或每 8KB 批量推送一次,而不是每字节都推;平台网关→前端同理
  4. **pty 生命周期跟着容器走**:容器销毁时 docker 自动 SIGKILL 所有 exec 进程(天然清理);Runner 进程崩溃后重启时**清理上次残留的 pty**(扫一遍容器里的 exec 进程,kill 掉)
  5. **AI 输出与终端并发**(双通道):
     - 用户输入:浏览器 → 平台 → Runner → pty stdin
     - AI 命令输出:**不经过 pty**,而是 Runner 通过 `docker exec`(非 pty 模式)执行命令,读 stdout,**转发到终端频道**;前端 xterm.js 渲染为只读文本(前缀 `[ai]` 高亮)
     - **两条数据流分离**:用户输入走 pty;AI 输出走 Runner 转发到终端频道,互不干扰
  6. **Runner offline 时优雅降级**:前端显示"Runner offline,终端不可用";Runner 恢复后自动重连,pty 状态保留
  7. **滚动缓冲**:平台后端**不缓存**终端输出,依赖 xterm.js 前端缓冲(5000 行);刷新页面后**重新开始**(V1 简单)
- **性能估算**:
  - 单实例 50 容器 × 5 Tab = 250 并发 ws,FastAPI + uvloop 轻松扛住
  - 链路延迟:LAN 内 ~10ms,跨机房 50-200ms;**用户无感**(xterm.js 本地回显)
  - 高频输出:> 1000 行/秒丢弃中间,保留首尾(PRD 已定)
- **业界验证**:GitHub Codespaces / Gitpod / CodeSandbox 都是这个模式(容器跑在远端,通过 Runner/ws-manager/pitcher 代理),终端体验都很好,用户感觉不到容器不在本地
- **前端关键库**:
  - `xterm` + `xterm-addon-fit`(自适应大小) + `xterm-addon-web-links`(可点击链接)
  - **不用** `xterm-for-react`(已停止维护),直接用官方 xterm + addons,自己写 React 包装组件
- **后端关键实现**(Runner 侧):
  - Runner 接收平台的 WebSocket 消息 `{"type": "terminal_input", "session_id": ..., "data": ...}` → 写入 pty stdin
  - Runner 读 pty stdout/stderr → 批量缓冲(50ms/8KB)→ 发送 `{"type": "terminal_output", "session_id": ..., "data": ...}` 到平台 → 平台转发到前端
  - pty 通过 `docker SDK exec_create(container_id, cmd=["/bin/bash"], tty=True) + exec_start(exec_id)` 创建
- **影响的需求点**:R9
- **冲突点**:无
- **状态**:✅ 已确认(用户确认;Runner 架构下关键实现要点已补充)

## 数据模型概要

(表级:新表清单 + 用途 + 关键关系;字段级定义归 rd-plan)

| 表 | 类型 | 用途 | 关键关系 |
|---|---|---|---|
| **users** | 新增 | 用户主表(R1) | 1:N project_members, 1:N tasks(created_by), 1:N usage_records |
| **projects** | 新增 | 项目主表(R2) | 1:N project_repos, 1:N requirements, 1:N project_members, 1:N model_configs, 1:N project_skills |
| **project_repos** | 新增 | 项目-仓库关联表(R2) | N:1 projects, 1:N tasks(通过 repo_ids) |
| **project_members** | 新增 | 项目成员表(R12) | N:1 projects, N:1 users |
| **requirements** | 新增 | 需求主表(R3) | N:1 projects, 1:N tasks |
| **tasks** | 新增 | 任务主表(R4,统一四种类型) | N:1 requirements, N:1 projects, N:1 users(created_by), 1:1 containers(运行时), N:1 runners(运行时) |
| **task_uploaded_files** | 新增 | 任务上传文件表(R4) | N:1 tasks, N:1 users(uploaded_by) |
| **task_messages** | 新增 | 任务消息表(R4,对话历史) | N:1 tasks |
| **containers** | 新增 | 容器实例表(R8) | N:1 projects, 1:1 tasks(运行时), N:1 users(创建者), N:1 runners |
| **runners** | 新增 | Runner 节点表(R16) | 1:N containers |
| **model_configs** | 新增 | 模型配置表(R13) | N:1 projects, 1:N usage_records |
| **routes** | 新增 | 网关路由表(R15) | N:1 projects, N:1 tasks(preview 时), N:1 containers, N:1 runners |
| **knowledge_entries** | 新增 | 知识条目表(R14) | N:1 projects(可空=平台级), N:1 requirements(来源) |
| **usage_records** | 新增 | 用量记录表(R14) | N:1 users, N:1 projects, N:1 model_configs, N:1 tasks(可空) |
| **audit_logs** | 新增 | 审计日志表 | N:1 users, N:1 projects(可空) |
| **knowledge_bases** | 新增 | 项目知识库(R20,source_type=blank/repo_import) | N:1 projects, 1:N knowledge_docs |
| **knowledge_docs** | 新增 | 知识库页面(R20,树形 path,导入型只读) | N:1 knowledge_bases |
| **invitations** | 新增 | 邀请表(R1/R12) | N:1 users(被邀请人,可空=未注册), N:1 projects(可空=平台级), N:1 users(invited_by) |
| **platform_settings** | 新增 | 平台设置表(单例,R2 GitLab 配置) | - |
| **skills** | 新增 | Skills 表(R17) | 1:N project_skills |
| **project_skills** | 新增 | 项目-Skills 关联表(R17) | N:1 projects, N:1 skills |

**关键设计**:
- **tasks** 表统一四种类型(requirement/dev/test/release),通过 `type` 字段区分,共享大部分字段;特定字段(如 test_cases/deploy_port)用 JSONB 存到 `extended_attributes` 字段
- **containers** 与 **tasks** 运行时 1:1,但部署中任务(R7)的容器在任务 done 后仍存在,因此 `containers.task_id` 可空(部署中容器脱离任务独立存在)
- **containers.runner_id** 记录容器运行在哪个 Runner 上;**runners** 表存 Runner 节点信息(name/role/status/心跳)
- **project_repos** 的 `role` 字段(main/test/docs/other)决定任务容器内的挂载路径(R6)
- **task_uploaded_files** 记录任务上传的文件(文件名/大小/容器内路径);**task_messages** 记录任务对话历史(role/content/file_refs/tool_calls)
- **skills** 表存 Skills(scope=platform/project);**project_skills** 是项目与 Skills 的关联表(项目安装了哪些 Skills)
- **projects.mcp_config_encrypted** 存项目级 MCP server 配置(JSON),AES-256-GCM 加密
- **audit_logs** 记录所有敏感操作(登录/项目增删/成员变更/部署/模型配置变更/驳回/强制 push),保留 1 年
- **users.role**(superadmin/user,R19/D16)与 **users.token_version**(D17 禁用即全失效);超管在项目 guard 中视为虚拟 owner,不做成员关系冗余
- **knowledge_bases.source_type** 决定读写权限:repo_import 只读 + 手动同步(R20/D18);`knowledge_docs.source_file_path` 记录导入来源
- **usage_records** 仅做 token 用量统计(R4 total_tokens 汇总),不涉及计费(PRD 范围外)

## 接口概要

(接口级:新建/复用/变更清单 + 用途;契约细节归 rd-plan)

### 认证与用户

| 接口 | 方法 | 用途 | 新建/复用/变更 |
|---|---|---|---|
| /api/auth/register | POST | 注册(邀请制,需 invitation_token) | 新建 |
| /api/auth/login | POST | 登录(账号+密码,返回 JWT) | 新建 |
| /api/auth/refresh | POST | 刷新 access token | 新建 |
| /api/auth/logout | POST | 登出 | 新建 |
| /api/auth/forgot-password | POST | **V1 不建**:PRD R1 定为 V2 短信找回,V1 降级"联系管理员" | 不建 |
| /api/auth/reset-password | POST | 重置密码(用邮件 token) | 新建 |
| /api/users/me | GET/PATCH | 获取/更新个人信息 | 新建 |
| /api/users/me/gitlab-token | PUT/DELETE | 绑定/解绑 GitLab token | 新建 |
| /api/users/me/notification-settings | PUT | 配置钉钉 webhook | 新建 |

### 平台设置(超管)

| 接口 | 方法 | 用途 | 新建/复用/变更 |
|---|---|---|---|
| /api/admin/platform-settings | GET/PUT | 查看/更新平台设置(GitLab 实例/bot token) | 新建 |
| /api/admin/users | GET | 用户列表(超管) | 新建 |
| /api/admin/users/{id}/status | PATCH | 禁用/启用用户(D17 禁用即全失效,最后一个超管保护) | 新建 |
| /api/admin/invitations | GET/POST | 平台注册邀请管理(Q5 超管邀请) | 新建 |
| /api/admin/usage | GET | 全平台用量统计 | 新建 |
| /api/admin/audit-logs | GET | 审计日志查询 | 新建 |

### 项目

| 接口 | 方法 | 用途 | 新建/复用/变更 |
|---|---|---|---|
| /api/projects | GET/POST | 项目列表/创建 | 新建 |
| /api/projects/{id} | GET/PATCH/DELETE | 项目详情/更新/删除 | 新建 |
| /api/projects/{id}/repos | GET/POST | 项目仓库列表/追加绑定 | 新建 |
| /api/projects/{id}/repos/{repo_id} | DELETE | 解绑仓库(非 main) | 新建 |
| /api/projects/{id}/members | GET/POST | 成员列表/邀请 | 新建 |
| /api/projects/{id}/members/{user_id} | PATCH/DELETE | 改角色/移除成员 | 新建 |
| /api/projects/{id}/model-configs | GET/POST | 模型配置列表/创建 | 新建 |
| /api/projects/{id}/model-configs/{config_id} | PATCH/DELETE | 更新/删除模型配置 | 新建 |
| /api/projects/{id}/usage | GET | 项目用量统计 | 新建 |

### 需求

| 接口 | 方法 | 用途 | 新建/复用/变更 |
|---|---|---|---|
| /api/projects/{pid}/requirements | GET/POST | 需求列表/创建 | 新建 |
| /api/requirements/{id} | GET/PATCH | 需求详情/更新 | 新建 |
| /api/requirements/{id}/polish | POST | 启动打磨任务(创建 type=requirement 任务) | 新建 |
| /api/requirements/{id}/submit-review | POST | 提交评审 | 新建 |
| /api/requirements/{id}/review | POST | 评审通过/驳回 | 新建 |
| /api/requirements/{id}/cancel | POST | 取消需求 | 新建 |
| /api/requirements/{id}/archive | GET | 归档页数据(时间线) | 新建 |

### 任务

| 接口 | 方法 | 用途 | 新建/复用/变更 |
|---|---|---|---|
| /api/requirements/{rid}/tasks | GET/POST | 任务列表/创建(dev/test/release) | 新建 |
| /api/tasks/{id} | GET | 任务详情 | 新建 |
| /api/tasks/{id}/stop | POST | 停止任务 | 新建 |
| /api/tasks/{id}/retry | POST | 重试任务 | 新建 |
| /api/tasks/{id}/messages | GET | 任务对话历史 | 新建 |
| /api/tasks/{id}/reject-to-dev | POST | 测试任务驳回回开发 | 新建 |
| /api/tasks/{id}/offline | POST | 发布任务下线 | 新建 |
| **/api/tasks/{id}/files/upload** | **POST** | **上传文件到任务容器 `/tmp/uploads/{task_id}/`**(multipart/form-data,单文件 ≤ 50MB) | **新建** |
| **/api/tasks/{id}/files/uploads** | **GET** | **列出当前任务已上传的文件** | **新建** |
| **/api/tasks/{id}/files/uploads/{file_id}** | **GET/DELETE** | **下载/删除已上传的文件** | **新建** |

### 容器(内部,不暴露给用户)

| 接口 | 方法 | 用途 | 新建/复用/变更 |
|---|---|---|---|
| /api/containers/{id}/status | GET | 容器状态查询(内部) | 新建 |
| /api/containers/{id}/logs | GET | 容器日志(内部) | 新建 |

### 文件与代码(编辑器)

| 接口 | 方法 | 用途 | 新建/复用/变更 |
|---|---|---|---|
| /api/projects/{pid}/files | GET | 项目模式:文件树(GitLab API 代理) | 新建 |
| /api/projects/{pid}/files/content | GET | 项目模式:文件内容(GitLab API 代理) | 新建 |
| /api/tasks/{tid}/files | GET | 任务模式:文件树(容器内) | 新建 |
| /api/tasks/{tid}/files/content | GET/PUT | 任务模式:文件内容读/写(容器内) | 新建 |
| /api/tasks/{tid}/files/diff | GET | 任务级 diff 视图 | 新建 |

### 知识库

| 接口 | 方法 | 用途 | 新建/复用/变更 |
|---|---|---|---|
| /api/projects/{pid}/knowledge | GET/POST | 项目知识库列表/创建 | 新建 |
| /api/knowledge | GET | 平台知识库列表(搜索) | 新建 |
| /api/knowledge/{id} | GET/PATCH/DELETE | 知识条目详情/更新/删除 | 新建 |
| /api/knowledge/{id}/publish | POST | 发布知识条目(draft → published) | 新建 |
| /api/knowledge/{id}/promote | POST | 提升到平台级(owner) | 新建 |

### 项目知识库空间(R20,D18;与上方"知识条目"并存,命名隔离)

| 接口 | 方法 | 用途 | 新建/复用/变更 |
|---|---|---|---|
| /api/projects/{pid}/knowledge-bases | GET/POST | 知识库列表/创建(blank 或带 source_config) | 新建 |
| /api/projects/{pid}/knowledge-bases/{id} | GET/PATCH/DELETE | 详情(树)/改名/删除 | 新建 |
| /api/projects/{pid}/knowledge-bases/{id}/import | POST | 目录导入(后台任务) | 新建 |
| /api/projects/{pid}/knowledge-bases/{id}/sync | POST | 重新导入(手动同步) | 新建 |
| /api/knowledge-bases/{id}/docs | GET/POST | 页面树/新建页面(blank) | 新建 |
| /api/knowledge-bases/{id}/docs/{doc_id} | GET/PUT/DELETE | 页面读/改/删(blank;repo_import 写操作 403) | 新建 |
| /api/knowledge-bases/{id}/search | GET | 库内标题+全文搜索 | 新建 |

### 全局工作台与四维管理(R21/R22,D19)

| 接口 | 方法 | 用途 | 新建/复用/变更 |
|---|---|---|---|
| /api/dashboard/summary | GET | R21:四类卡片统计(created_by=me)+ 每类最近 5 条 | 新建 |
| /api/manage/requirements | GET | R22 聚合列表(成员项目过滤 + 项目/状态/关键字筛选 + 分页) | 新建 |
| /api/manage/tasks | GET | R22 聚合列表(全部任务类型) | 新建 |
| /api/manage/tests | GET | R22 聚合列表(type=test) | 新建 |
| /api/manage/releases | GET | R22 聚合列表(type=release) | 新建 |
| (快速创建) | POST | 复用既有 /api/projects/{pid}/requirements、/api/requirements/{rid}/tasks,project_id 由表单选定;前置校验与项目内一致 | 复用 |

### MCP server 与 Skills

| 接口 | 方法 | 用途 | 新建/复用/变更 |
|---|---|---|---|
| /api/projects/{pid}/mcp-config | GET/PUT | 项目级 MCP server 配置(读/写,加密) | 新建 |
| /api/projects/{pid}/mcp-config/templates | GET | 常用 MCP server 模板列表(PostgreSQL/Redis/GitHub 等) | 新建 |
| /api/skills | GET | 平台级 Skills 市场列表(scope=platform) | 新建 |
| /api/skills/{id} | GET | Skill 详情(含内容) | 新建 |
| /api/projects/{pid}/skills | GET/POST | 项目已安装 Skills 列表/安装平台级 Skill | 新建 |
| /api/projects/{pid}/skills/upload | POST | 上传项目级自定义 Skill(.md 文件) | 新建 |
| /api/projects/{pid}/skills/{skill_id} | DELETE | 卸载 Skill | 新建 |
| /api/admin/skills | GET/POST | 平台级 Skills 管理(超管) | 新建 |
| /api/admin/skills/{id} | PATCH/DELETE | 平台级 Skills 更新/删除(超管) | 新建 |

### WebSocket 网关

| 接口 | 方法 | 用途 | 新建/复用/变更 |
|---|---|---|---|
| /ws | WS | 统一 WebSocket 入口(鉴权 + 频道路由) | 新建 |
| /ws/terminal/{session_id} | WS | 终端 TTY(通过 /ws 频道转发到 Runner 上的 docker exec) | 新建 |
| /ws/tasks/{tid}/events | WS | 任务事件流(AI 工具调用/状态变更) | 新建 |
| /ws/tasks/{tid}/files | WS | 文件 watcher 事件 | 新建 |
| /ws/preview/{route_id}/* | WS | 预览 HMR 透传(代理到 Runner 上的容器内 dev server) | 新建 |
| **/ws/runner** | **WS** | **Runner 与平台的 WebSocket 通道**(注册/心跳/任务指令/容器事件回传) | **新建** |

### GitLab Webhook

| 接口 | 方法 | 用途 | 新建/复用/变更 |
|---|---|---|---|
| /api/webhooks/gitlab | POST | 接收 GitLab webhook(push/MR/note) | 新建 |

### Runner 管理(超管)

| 接口 | 方法 | 用途 | 新建/复用/变更 |
|---|---|---|---|
| /api/admin/runners | GET/POST | Runner 列表/创建(生成 token) | 新建 |
| /api/admin/runners/{id} | GET/DELETE | Runner 详情/删除 | 新建 |
| /api/admin/runners/{id}/reset-token | POST | 重置 Runner token | 新建 |
| /api/admin/runners/{id}/disable | POST | 禁用 Runner(不再调度新任务) | 新建 |

## 开放问题

(调研未决、需用户补充信息的问题;清零才能确认;无则写"无")

无——所有决策点已给出候选方案与推荐,待用户确认。

## 变更记录

| 日期 | 变更 | 原因 |
|---|---|---|
| 2026-09-20 | 初始版本 | rd-arch 启动,基于 PRD v4(已确认) |
| 2026-09-21 | D1–D11 全部确认;D2 数据库改为 MySQL 8.0 + asyncmy(用户点名);D10 容器镜像改为基于 `mcr.microsoft.com/devcontainer/universal:linux` 加装 Claude CLI(用户指定);新增 D11 Web 终端方案;补充任务创建时环境变量注入细节(LLM_*/ANTHROPIC_*/GITLAB_* 双变量注入 + git credential.helper);ARCH 状态改为"已确认" | 用户逐条确认 |
| 2026-09-21 | **D6 重写**(单机 Docker → Runner 架构);**新增 D12 文件上传与 @ 引用**(平台中转 + 混合注入策略);**新增 D13 Runner 通信协议**(WebSocket + 注册/心跳/指令);**新增 D14 部署 Runner 专用化**(role=deploy);新增表 `task_uploaded_files`/`task_messages`/`runners`;新增接口 `/api/tasks/{id}/files/upload` 等 3 个 + `/api/admin/runners/*` 4 个 + `/ws/runner` | 用户补充:文件上传 + Runner 架构 |
| 2026-09-21 | **D11 补充 Runner 架构下的终端实现要点**:xterm.js 本地回显(用户无感延迟)、pty 会话复用(session_id attach)、Runner 本地缓冲 + 批量推送(50ms/8KB)、pty 生命周期跟着容器走、AI 输出与用户输入双通道分离、Runner offline 优雅降级、业界验证(GitHub Codespaces/Gitpod/CodeSandbox 都是这个模式) | 用户问"Runner 模式下终端效果能否保证",补充关键实现要点 |
| 2026-09-21 | **新增 R17(PR D)+ D15(ARCH)**:MCP server 与 Skills 管理;**混合策略**(镜像预装 + 项目级配置注入 + Skills 市场);新增表 `skills`/`project_skills`;新增接口 `/api/projects/{pid}/mcp-config` + `/api/skills/*` + `/api/projects/{pid}/skills/*` 等 8 个;**MCP server 分类**(无状态镜像预装 / 项目特定注入 / 有状态远程化 V2);**Skills 分类**(平台级市场 / 项目级上传);敏感信息 AES-256-GCM 加密 + 接口打码 | 用户补充:MCP server + Skills 管理 |
| 2026-09-21 | **PRD 增量对齐(R19–R22)**:新增 D16 权限模型(双层 Guard,超管=虚拟 owner)、D17 token_version 立即失效、D18 知识库双表+后台导入、D19 聚合视图无新表;新增表 `knowledge_bases`/`knowledge_docs`;新增接口 `/api/admin/users/{id}/status`、`/api/admin/invitations`、`/api/dashboard/summary`、`/api/manage/*` 4 个、`/api/*/knowledge-bases/*` 7 个;修正 forgot-password 为 V1 不建(对齐 PRD R1);清理重复粘贴的 D14 块;现状地图更新为本仓库路径 + design.md(shadcn tokens)资产;**D20 网关链路简化(取消 Runner 本地代理)待人工确认** | PRD 增量:权限体系/项目知识库/Dashboard/四维管理菜单 |
| 2026-09-21 | **D20 用户拍板:取消 Runner 本地代理**(方案 A);D6/D14 同步修订:预览 upstream 直连 `runner_host:mapped_port`,部署容器直接映射宿主机 `deploy_port`;PRD R15/R16 已同步回写;ARCH 全部决策点(D1–D20)已确认 | 人工核对确认 |
| 2026-09-21 | PRD 增量 Q26(文档目录规范)/Q27(文件树变更视图)架构快筛:**9 类全绿,无新增系统级决策**——slug 生成与目录命名规则、变更清单聚合接口细节归 rd-plan(按 D6 exec 通道实现);ARCH 维持已确认 | 例行增量复核 |
