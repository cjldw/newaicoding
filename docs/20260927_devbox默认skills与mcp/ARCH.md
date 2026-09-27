# 架构设计:devbox 镜像默认 rd-flow plugin 与 MySQL/Figma MCP 预装

> PRD:./PRD.md
> 创建日期:2026-09-27
> 状态:**已确认**(2026-09-27,D4/D5 按推荐方案 A 拍板,开放问题为空)

## 现状地图

(rd-plan 直接复用本节,不重探)

### 涉及的既有模块

- **docker/devbox/Dockerfile**:基础镜像 devcontainers/typescript-node:dev-bookworm,**USER node(uid 1000,HOME=/home/node,R8.F1 实测)**;已预装 Claude CLI、3 个 MCP 包(npm -g,从未写配置)、平台 skills(COPY 到 /home/node/.claude/skills/)。本次改动点:追加 plugin 安装、MCP 配置文件、新 server 包
- **runner/container_manager.py**:claude_inject(:597-636,写 /root/.claude/skills/*.md + 整段替换 /root/.claude.json 的 mcpServers)、probe_claude(:638-719,临时容器探测 /root/.claude/skills 一级目录 + /root/.claude.json mcpServers)、exec 全链路(316/532/950)**均不指定 user**。本次改动点:路径基准修正 + mcpServers 合并语义 + probe 覆盖 plugin
- **backend task_service.py**:env 组装(custom_env_vars 铺底 :93-113/:382-401)+ 注入触发 inject_task_claude_assets(:430-462)。本次改动点:无(env 链路现成)
- **backend/system_asset_service.py**:采集编排(锁/冷却/先清后插,DEFAULT_PROBE_IMAGE=platform/devbox:v1 :35)。本次改动点:仅随 runner probe 扩展间接受益,自身近零改动
- **backend/platform_settings_service.py**:custom_env_vars(envmap 白名单,≤50 键,值≤2048,明文回显;保留键 RESERVED_ENV_KEYS)。本次改动点:零代码,运营配置 7 个变量
- **backend/mcp_service.py**:项目 MCP AES-GCM 加密存取 + 4 内置模板(postgres/redis/github/slack)。本次改动点:可顺手新增 mysql/figma 模板(可选,非必须)
- **frontend**(McpConfigManagement/SkillsMarket/TaskChat):系统级展示与 /skills /mcp 候选合并(R7)已实现,数据源 GET /api/system-assets。本次改动点:近零(/root 文案随 D4 修正)

### 可复用资产

- custom_env_vars 注入链:平台设置页编辑 → task_service env 铺底 → 容器 environment(零新开发)
- 注入链:handle_container_started → inject_task_claude_assets → runner claude_inject(幂等,失败降级不阻塞)
- 采集链:POST /api/admin/system-assets/collect → probe_claude 临时容器 → claude_system_assets 表 → GET /api/system-assets → AI 对话候选合并(R7 前端已并)
- AI 对话候选:/skills ∪ sysAssets.skills、/mcp ∪ sysAssets.mcps,内置徽标(TaskChat.tsx:343-369)

### 冲突点

- **【阻断】配置根路径错位**:镜像与 claude 进程在 node(/home/node/.claude*),runner 注入/探测硬编码 /root/.claude* 且 exec 不带 user(以 node 执行,node 对 /root 无写权限,标准 Debian 700)→ 注入大概率一直失败(降级静默)、探测大概率一直采空。基础镜像 /root 实际权限仓库内无实测记录(rd-plan 实测确认,但架构按"错位成立"处理)
- **【阻断】mcpServers 整段替换**:claude_inject 读到既有配置后 `existing["mcpServers"]=新配置` 整段覆盖,预置项会被项目注入抹掉
- 存量 3 MCP(filesystem/github/brave-search)只有包没有配置,从未生效
- 前端 2 处文案硬编码「/root/.claude.json」(McpConfigManagement.tsx:6,134)

## 决策点清单

### D1:MCP server 分发形态——镜像内预装,禁运行时外网拉取
- **类别**:集成依赖
- **候选方案**:
  | 方案 | 一句话 | 优点 | 缺点 |
  |---|---|---|---|
  | A 镜像内预装 | npm -g(或 pip/uv 本地装)进镜像,配置 command 直指本地可执行 | 容器运行零外网依赖,启动快,版本随镜像固定 | 镜像变大;换实现需重建镜像 |
  | B 运行时 npx/uvx 拉取 | 配置 command 为 npx/uvx,容器启动时从 npm/PyPI 拉 | 镜像小 | 任务容器需出网;首启慢;版本漂移;内网环境不可用 |
- **推荐**:A。理由:任务容器运行环境不保证出网(与 plugin 构建期安装同一原则);现有 3 个 MCP 即 npm -g 形态,沿约定
- **影响的需求点**:R2
- **冲突点**:无(与现状 npm -g 约定一致)
- **状态**:✅ 自动确认(依据:PRD 已拍板"包随镜像安装",现状 npm -g 惯例)

### D2:MySQL 只读双层防线
- **类别**:安全权限
- **候选方案**:
  | 方案 | 一句话 | 优点 | 缺点 |
  |---|---|---|---|
  | A 仅 DBA 只读账号 | 依赖 DBA 侧授权只读账号 | 平台零实现 | server 若无只读模式,误写风险全押账号权限 |
  | B 仅 server 只读模式 | 选支持只读的实现并开启 | 平台内可控 | 配置错误即失去防线 |
  | C 双层叠加 | DBA 只读账号(根本)+ server 只读模式(第二道) | 纵深防御 | 需选型时筛"支持只读"的实现 |
- **推荐**:C。账号只读是根本防线(平台外保证),server 只读模式是应用层第二道;选型(rd-plan)以此为准入条件
- **影响的需求点**:R2
- **冲突点**:无
- **状态**:✅ 自动确认(依据:PRD 已拍板只读,层次明确化)

### D3:claude_inject mcpServers 合并语义
- **类别**:冲突检测
- **候选方案**:
  | 方案 | 一句话 | 优点 | 缺点 |
  |---|---|---|---|
  | A 按名合并,项目级优先 | `existing.update(项目级)`,预置项保留 | 预置与项目配置共存;语义可预期 | 同名时项目级"藏住"预置项(可接受,PRD 已拍板) |
  | B 保持整段替换 | 现状不动 | 零改动 | 预置项被项目注入抹掉,R2 不成立 |
- **推荐**:A。skills 注入语义不变(平台 scope 排前/项目排后,后写覆盖,现状即合并覆盖语义)
- **影响的需求点**:R2、R3
- **冲突点**:即"整段替换"冲突本身,本决策消除之
- **状态**:✅ 自动确认(依据:PRD R3 已拍板方向)

### D4:claude 配置根路径统一(阻断修复)
- **类别**:冲突检测/演进兼容
- **候选方案**:
  | 方案 | 一句话 | 优点 | 缺点 |
  |---|---|---|---|
  | A 统一到运行用户 HOME | 镜像一切 claude 资产(skills/plugin/MCP 配置)装在 /home/node/.claude*;runner 注入/探测路径改为 $HOME 动态展开(或 /home/node) | 与镜像 USER node、claude 进程身份、R8.F1 实测、web 终端身份全部一致;改 runner 常量+镜像层,影响面清晰 | 修 6 处 runner 硬编码 + 2 处 backend 注释 + 2 处前端文案 |
  | B 统一到 root | 镜像改 USER root,claude 以 root 跑,资产进 /root | runner 代码零改动 | 整个容器运行身份变 root:web 终端/git clone 产物 owner 变 root;Claude CLI 对 root+跳权限有安全限制;安全面扩大 |
  | C 注入提权写 /root | exec 加 user=root,仅注入/探测提权 | runner 改动最小 | claude 进程仍 node 读不到 /root,错位仍在,不可行 |
- **推荐**:A。全链路身份唯一(node),claude CLI 天然读得到;C 逻辑不成立,B 动容器运行身份伤终端/编辑器/git 语义
- **影响的需求点**:R1、R2、R4(三者的安装/预置/探测位置统一由本决策定)
- **冲突点**:即现状地图阻断冲突;修复后注入链/采集链在真实镜像上恢复可用
- **状态**:✅ 已确认(2026-09-27,方案 A)

### D5:镜像 tag 演进与存量容器并行
- **类别**:演进兼容
- **候选方案**:
  | 方案 | 一句话 | 优点 | 缺点 |
  |---|---|---|---|
  | A 升 v2 + 常量同步 | tag 升 platform/devbox:v2,同步 5 处硬编码默认值(models/container.py 列默认、container_service.DEFAULT_IMAGE、system_asset_service.DEFAULT_PROBE_IMAGE、runner main×2/container_manager) | 新旧镜像并行期可控(存量容器用 v1 跑完销毁,新任务用 v2);采集 image_tag 可辨版本 | 改 5 处 + 构建推两镜像过渡 |
  | B 沿用 v1 覆盖推送 | 重新 build 同 tag 推送 | 零代码改动 | 版本不可辨;存量旧 v1 容器与新 v1 并存同名不同内容,采集 image_tag 失真;回滚困难 |
- **推荐**:A。一次性 5 处常量改动成本极低,换来版本可辨与可回滚;system-assets 旧采集数据随重新采集自然覆盖(PRD R4 现有语义),无需迁移
- **影响的需求点**:R1、R4(验收环境)
- **冲突点**:无
- **状态**:✅ 已确认(2026-09-27,方案 A)

## 数据模型概要

| 表 | 类型 | 用途 | 关键关系 |
|---|---|---|---|
| claude_system_assets | 复用 | 系统级采集快照,probe 扩展后含 plugin 条目 | 无变更 |
| platform_settings(custom_env_vars) | 复用 | 7 个新变量运营配置(envmap) | 无变更 |

无新表、无改表、无迁移。

## 接口概要

| 接口/指令 | 方法 | 用途 | 新建/复用/变更 |
|---|---|---|---|
| runner exec_tool claude_inject | - | 注入 skills/MCP 配置 | 复用;mcpServers 语义变更(整段替换→按名合并,按 D3)、路径基准变更(按 D4) |
| runner probe_claude | - | 系统级采集探测 | 复用;探测范围变更(覆盖 plugin)与路径基准变更(按 D4) |
| POST /api/admin/system-assets/collect | POST | 触发采集 | 复用不变 |
| GET /api/system-assets | GET | 系统级列表(候选合并数据源) | 复用不变 |
| GET/PUT /api/admin/platform-settings | GET/PUT | custom_env_vars 配置 7 变量 | 复用不变(运营动作) |

## 开放问题

(无——rd-plan 实测清单:基础镜像 /root 权限与 $HOME 展开、构建期 claude plugin 免登录验证、${VAR} 展开与配置文件格式、MySQL 只读/Figma server 选型、D5 的 tag 落点确认)

## 变更记录

| 日期 | 变更 | 原因 |
|---|---|---|
| 2026-09-27 | 初始版本(D1-D5;D1/D2/D3 自动确认) | PRD 已确认后架构调研 |
| 2026-09-27 | D4/D5 人工确认(均方案 A),状态改已确认 | 用户核对通过 |
