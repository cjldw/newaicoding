# PRD:devbox 镜像默认 rd-flow plugin 与 MySQL/Figma MCP 预装

> 创建日期:2026-09-27
> 状态:**已确认**(2026-09-27 访谈收口,待确认清单为空)
> 关联:平台主 PRD R17(Skills/MCP 接入)、R32(AI 对话 /skills、/mcp);《20260926_skills市场安装》(已实现)、《20260927_系统级skills与mcp列表》(采集链路已实现)

## 背景与目标

devbox 任务容器当前仅内置平台官方 skills 与 3 个通用 MCP 包(filesystem/github/brave-search,**只装了包从未写配置,实际从未生效**)。研发全流程(rd-flow)与数据库/Figma 场景能力缺失。本需求:

1. 把团队自建 rd-flow plugin 预装进 devbox 基础镜像(构建期)
2. 预置 6 个 MCP 的 mcpServers 配置(mysql_dev/mysql_beta/figma 新增 + 存量 3 个激活),认证走平台「自定义变量」机制
3. 装完后「系统级已装列表」能采集到,AI 对话框 /skills、/mcp 候选能列出并使用

衡量成功:新构建的镜像起任务容器后,AI 对话中直接可用 rd-flow 的 skills/commands、可查 dev/beta 库(只读)、可读 Figma 链接;系统级已装列表完整反映上述能力。

## 用户故事

1. 作为研发成员,我希望任务容器开箱自带 rd-flow 研发全流程 skills,以便 AI 对话直接走需求/计划/开发流程
2. 作为研发成员,我希望 AI 对话能直接查 dev/beta MySQL 库,以便开发时随时核对表结构与数据
3. 作为研发成员,我希望 AI 对话能解析 Figma 链接,以便按设计稿实现 UI
4. 作为超管,我希望在平台设置页配好 MySQL/Figma 凭据后,所有任务容器自动获得这些能力,以便无需逐项目配置

## 已确认决策(2026-09-27 访谈)

| 事项 | 结论 |
|---|---|
| 镜像范围 | **仅 devbox 基础镜像**;runner 镜像保持薄代理不装 |
| rd-flow plugin | 镜像构建期 `claude plugin marketplace add` + `claude plugins install`;marketplace 地址做 build ARG(默认 `http://47.111.69.64/ai/rd-flow.git`) |
| MCP 配置归属 | **镜像构建期预置** mcpServers 配置文件(env 值 `${VAR}` 引用);运行时注入链改为「按名合并,项目级优先」防覆盖 |
| MySQL 变量清单 | 6 变量:DEV_HOST/BETA_HOST/PORT/USER/PASSWORD/DATABASE;除 HOST 外 dev/beta 共用 |
| 凭据存储 | 沿用平台 `custom_env_vars`(超管设置页配置,容器创建时自动注入;明文存/明文回显,本次不改脱敏) |
| 可用范围 | 全局默认可用,所有项目任务容器天然可用,**不做项目级开关** |
| 缺变量降级 | 静默降级:MCP 条目仍在(采集/候选可见),server 启动失败不阻塞容器创建与任务执行 |
| 库权限 | MySQL MCP **只读**(查表结构/SELECT;若选型不支持只读模式,rd-plan 优先选支持的实现) |
| 采集扩展 | probe_claude 扩展覆盖 plugin 形态安装的 skills;顺带校准 /root 与 /home/node 路径错位 |
| 存量 3 MCP | filesystem/github/brave-search 本次一并写配置激活 |
| MCP 选型 | mysql/figma 的 server 实现包未指定,rd-plan 调研实测后定(镜像需 npm/uvx 可装、支持只读、env 认证) |

## 需求点清单

### R1:devbox 镜像预装 rd-flow plugin

- **描述**:Dockerfile 构建期以运行用户执行 `claude plugin marketplace add {ARG}` + `claude plugins install rd-flow`,plugin 及其携带的 skills/commands 随镜像分发,任务容器内开箱可用
- **触发场景**:镜像构建(docker build);使用为任务容器内 AI 对话直接调用
- **前置条件**:构建机可访问 marketplace 地址(当前为 `http://47.111.69.64`);基础镜像内 Claude CLI 已装(现状已有)
- **边界定义**:
  - 做什么:marketplace 地址做成 `ARG RD_FLOW_MARKETPLACE`(带默认值);构建期安装并验证(plugin 列表可见);安装到镜像运行用户的 claude 目录
  - 不做什么:不做版本锁定(跟随 marketplace 默认);不做运行时安装/更新;runner 镜像不装;不改平台 plugin 管理功能
- **依赖**:无
- **异常与边界场景**:
  - 构建机不可达 marketplace → 构建失败(显式报错,不静默跳过)
  - 构建期 claude CLI 子命令不需要 API key 即可执行(rd-plan 实测验证;若需要则找免登录形态)
  - 安装用户与 claude 运行用户必须一致(与 R4 路径校准同一定,rd-plan 定 node 还是 root,统一即可)
- **验收标准**:
  1. `docker build --build-arg RD_FLOW_MARKETPLACE=<地址>` 构建成功;不传 ARG 用默认地址也成功
  2. 用新镜像起容器,`claude plugin list` 可见 rd-flow;其 skills/commands 在 claude 会话中可用
  3. R4 采集后,系统级已装列表包含 rd-flow 提供的 skills

### R2:devbox 镜像预置 MCP 配置(3 新增 + 3 存量激活)

- **描述**:镜像构建期写入 mcpServers 配置文件,预置 6 个 MCP 条目;认证值用 `${VAR}` 引用容器环境变量,平台「自定义变量」注入后即生效;MySQL 只读
- **触发场景**:镜像构建写配置;运行时超管在平台设置页「自定义变量」配置 6 个变量即完成接入
- **前置条件**:R2 依赖的 server 包随镜像安装(选型 rd-plan 定 npm/uvx 形态);custom_env_vars 机制已存在(平台设置页可配,容器创建时自动注入,现状链路)
- **边界定义**:
  - 做什么:
    - 新增 3 条:mcp_mysql_dev、mcp_mysql_beta(同一 server 实现,env 指向不同 HOST;只读模式)、figma(token 认证)
    - 激活存量 3 条:filesystem、github、brave-search(包已装,补配置;filesystem 限定 /workspace)
    - 配置文件落在 Claude 实际读取的配置位置(与 R1 安装用户统一)
  - 不做什么:不做项目级开关;不做凭据脱敏/加密改造;不做变量缺失时的配置裁剪(条目保留,静默降级)
- **字段定义**(新增 6 个自定义变量,超管经平台设置页「自定义变量」配置;shell 变量名,值 ≤2048 字符,沿用现有校验):
  | 变量名 | 必填 | 说明 |
  |---|---|---|
  | ENV_MCP_MYSQL_DEV_HOST | 是 | dev 库主机 |
  | ENV_MCP_MYSQL_BETA_HOST | 是 | beta 库主机 |
  | ENV_MCP_MYSQL_PORT | 是 | 端口(dev/beta 共用) |
  | ENV_MCP_MYSQL_USER | 是 | 账号(共用,需只读权限) |
  | ENV_MCP_MYSQL_PASSWORD | 是 | 密码(共用) |
  | ENV_MCP_MYSQL_DATABASE | 是 | 默认库(共用) |
  | ENV_MCP_FIGMA_TOKEN | 否 | Figma API token(未配则 figma MCP 不可用) |
- **交互规则**:
  | 场景/条件 | 行为/规则 | 结果/去向 |
  |---|---|---|
  | 6 个 MYSQL 变量已配置 | 容器创建时注入 env,mysql_dev/beta server 启动 | AI 对话可查库(只读) |
  | ENV_MCP_FIGMA_TOKEN 已配置 | figma server 启动 | AI 对话可解析 Figma 链接 |
  | 任一变量缺失 | 该 MCP server 启动失败,条目仍在配置中 | 容器创建/任务执行不受阻;对话中使用时报连接失败 |
  | 项目级 MCP 配置含同名 server | 项目级覆盖预置项(R3 合并语义) | 以项目级为准 |
- **依赖**:custom_env_vars 注入链(现状);R3(防覆盖)
- **异常与边界场景**:
  - `${VAR}` 展开行为、配置文件格式(.claude.json vs .mcp.json)由 rd-plan 实测定
  - MySQL 账号本身需 DBA 侧授权只读(平台外运营事项,PRD 记录前提)
  - 存量 3 个 MCP 激活后若与项目注入冲突,按 R3 项目级优先
- **验收标准**:
  1. 配置 6 变量后起任务容器,AI 对话可查 dev 与 beta 两库表结构/SELECT;写操作被拒
  2. 配置 FIGMA token 后,AI 对话贴 Figma 链接可解析
  3. 不配变量,容器创建与任务执行正常,对应 MCP 报连接失败
  4. 系统级采集(R4)列出全部 6 个 MCP

### R3:claude_inject 注入链合并逻辑改造

- **描述**:runner 侧 claude_inject 写 mcpServers 从「整段替换」改为「按 server 名合并,项目级优先」,保护镜像预置项不被项目注入覆盖
- **触发场景**:任务容器启动后的资产注入链(现状 handle_container_started → inject_task_claude_assets → claude_inject)
- **前置条件**:R2 预置配置存在
- **边界定义**:
  - 做什么:mcpServers 合并语义 = 预置项 ∪ 项目级,同名键项目级覆盖;skills 注入语义不变(项目级覆盖同名)
  - 不做什么:不改注入时机/失败降级策略(注入失败不阻塞容器就绪,现状保留)
- **依赖**:R2
- **异常与边界场景**:容器内配置文件不存在/非法 JSON → 按现状空对象兜底后合并写入
- **验收标准**:
  1. 预置 MCP + 项目级 MCP 并存可见
  2. 项目级配同名 server → 生效的是项目级配置
  3. 无项目级 MCP 的项目 → 仅预置项,行为同镜像原生

### R4:系统级采集扩展(覆盖 plugin + 路径校准)

- **描述**:probe_claude 采集扩展——skills 采集覆盖 plugin 形态安装项(rd-flow),并校准「探测路径 /root 与实际安装路径」错位,使系统级已装列表与 AI 对话候选完整反映镜像内置能力
- **触发场景**:超管「采集系统级列表」(现有入口);镜像内容变更后重新采集
- **前置条件**:R1、R2 已进镜像;采集链路已实现(临时容器探测、claude_system_assets 表、GET /api/system-assets)
- **边界定义**:
  - 做什么:skills 探测扩展到 plugin 目录(或 claude CLI 列举命令,rd-plan 实测定);统一镜像内安装用户与探测路径(消除 /root vs /home/node 错位);MCP 采集沿用 .claude.json mcpServers 读取(预置配置天然被采到)
  - 不做什么:不改采集触发机制(仍超管手动/首采);不做镜像版本 diff;不做采集自动回采
- **依赖**:R1、R2
- **异常与边界场景**:
  - plugin 提供的条目与平台 skills 同名 → 采集结果如实并列,AI 对话候选合并时同名项目配置优先(现有 R7 语义)
  - 探测临时容器以镜像默认用户运行 → 若默认用户无 /root 读权限,采集空;路径校准即为此兜底(rd-plan 实测确认)
- **验收标准**:
  1. 采集后,系统级已装列表包含:平台预装 skills + rd-flow plugin 的 skills/commands + 6 个 MCP
  2. AI 对话 /skills、/mcp 候选出现上述条目(内置徽标,链路现状)
  3. 重新采集覆盖旧数据(现状语义)

## 非功能需求

- 镜像体积增幅控制在合理范围(server 包 + plugin,不引入重型依赖)
- 构建可重复:marketplace 地址 ARG 化,构建命令与文档(README/DEPLOY.md)同步更新
- 凭据仅经 custom_env_vars 注入容器 env,不落入镜像层(构建期不写任何真实凭据)

## 范围外

- runner 镜像预装(保持薄代理)
- MCP server 实现包的选型细节与实测(rd-plan 承接:MySQL 只读实现、Figma 实现、${VAR} 展开验证、配置文件格式)
- 项目级启用/禁用开关(系统级天然可用)
- custom_env_vars 脱敏/加密改造(明文现状沿用)
- 镜像自动构建 CI/版本管理(tag 仍 platform/devbox:v1 或升级由 rd-plan/部署定)
- rd-flow plugin 自身的功能迭代

## 设计稿引用

- 无外部设计稿;系统级已装列表/AI 对话候选均为现有 UI,零新视觉

## 待确认清单

(空——2026-09-27 访谈全部收口:镜像范围、安装方式、变量清单、凭据存储、可用范围、降级行为、配置归属、采集扩展、存量激活、库只读)

## 确认记录(2026-09-27)

| 事项 | 结论 |
|---|---|
| 镜像范围 | 仅 devbox;runner 不动 |
| rd-flow plugin | 构建期装,marketplace 地址 ARG(默认 http://47.111.69.64/ai/rd-flow.git) |
| MCP 实现 | mysql/figma 选型留 rd-plan;MySQL 只读 |
| MySQL 变量 | 6 变量,除 HOST 外 dev/beta 共用;走 custom_env_vars |
| 可用范围/降级 | 全局默认可用;缺变量静默降级不阻断 |
| MCP 配置 | 镜像预置 + 注入链改按名合并(项目级优先);存量 3 MCP 一并激活 |
| 采集 | probe_claude 扩展覆盖 plugin,校准路径错位;系统级列表与 AI 对话候选自动生效 |

## 补充确认(2026-09-27,rd-plan 阶段)

| 事项 | 结论 |
|---|---|
| 变量清单扩容 | 补 2 个可选变量 ENV_MCP_GITHUB_TOKEN、ENV_MCP_BRAVE_API_KEY(存量 github/brave-search 激活需凭据源,原 7 变量未覆盖);变量清单定稿 9 个 |
| plugin 条目落库 | skills/commands 均以 claude_system_assets.kind="skill" 落库,detail.source="plugin" 标记(零迁移) |
| 平台 skills 修正 | 存量平台 skills 实际从未进镜像(COPY 源错位 + 平铺形态),修正工作纳入 DEVPLAN R1 |
