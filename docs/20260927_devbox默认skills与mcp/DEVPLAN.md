# 开发计划:devbox 镜像默认 rd-flow plugin 与 MySQL/Figma MCP 预装

> PRD:./PRD.md
> ARCH:./ARCH.md(D1–D5 已确认,分片按决策继承,不重开)
> 状态:**已确认**(2026-09-27 人工确认收口:R2 补 2 变量、R4 落库形态 kind=skill+source、R1 纳入平台 skills 修正;待确认清单为空)
> 创建日期:2026-09-27

## 需求概述

devbox 基础镜像构建期预装 rd-flow plugin(团队自建研发全流程)与 6 个 MCP 配置(mysql_dev/mysql_beta/figma 新增 + filesystem/github/brave-search 存量激活),认证凭据经平台 custom_env_vars 注入;顺带修复两处存量阻断:claude 配置根路径错位(/root vs /home/node,D4)与 mcpServers 整段替换覆盖预置项(D3 合并语义);probe 采集扩展覆盖 plugin 形态,系统级已装列表与 AI 对话 /skills、/mcp 候选完整反映镜像内置能力。缺变量静默降级,不阻塞容器创建与任务执行。

## 技术约定

(全局一份,分片不重复;rd-dev 全程遵循)

- **镜像基底**:devcontainers/typescript-node:dev-bookworm;构建期 USER root 装包,收尾切 `USER node`(uid 1000,HOME=/home/node,基础镜像默认,Dockerfile 未显式固定)
- **claude 资产根路径统一 /home/node(D4 决策)**:skills=`/home/node/.claude/skills/<name>/SKILL.md`(目录式,一名一目录)、配置=`/home/node/.claude.json`、plugin=claude CLI 默认 plugins 目录;**全链路禁止再出现 /root 硬编码**(runner 注入/探测、镜像 COPY、前端文案)
- **runner exec 全链路不指定 user**(exec_run 无 user 参数,以镜像默认用户 node 执行——D4 方案 A 成立前提,本次不改)
- **注入失败降级**:claude_inject 异常/超时(30s)不阻塞容器就绪,failed_sides 记录(现状保留)
- **MCP server 分发(D1 决策)**:构建期 npm -g 预装进镜像,配置 command 直指本地可执行,**禁运行时 npx/uvx 外网拉取**
- **MySQL 只读双层防线(D2 决策)**:DBA 只读账号(根本,平台外运营)+ server 只读模式(第二道,选型准入条件)
- **mcpServers 合并语义(D3 决策)**:预置 ∪ 项目级,同名键项目级覆盖;skills 注入语义不变(项目级后写覆盖)
- **镜像 tag(D5 决策)**:升 `platform/devbox:v2`;6 处生产常量 + alembic server_default migration + 5 个测试文件同步(代码精查勘误,ARCH 原"5 处"不含后两类)
- **custom_env_vars 现状约束**:≤50 键、值≤2048 字符、键名 `^[A-Za-z_][A-Za-z0-9_]*$`、不得占用 13 个保留键(RESERVED_ENV_KEYS)、明文存取明文回显(本次不改脱敏)
- **无外部设计稿**:系统级列表/AI 候选均为现有 UI,零新视觉

## 当前进度

**当前进度: 5/5 (100%) - 全部需求点完成(R1 构建冒烟 2026-09-28 转正;R5 container_image 后台可配置补登记)→ 引导 /rd-check。运行时遗留:R2/R3 的 MCP 凭据运营变量配置与 v2 镜像真机任务联调(平台外运营动作)**

| 需求点 | 名称 | 模块 | 状态 | 详情文件 |
|---|---|---|---|---|
| R1 | devbox 镜像预装 rd-flow plugin(+平台 skills 目录修正 + tag v2 落地) | M1 镜像构建 | ✅(2026-09-28 构建冒烟三场景 + 容器断言实跑转正) | ./DEVPLAN/R1.md |
| R2 | devbox 镜像预置 MCP 配置(3 新增 + 3 存量激活) | M1 镜像构建 | ✅(镜像内 6 键断言 PASS;凭据变量配置=平台外运营) | ./DEVPLAN/R2.md |
| R3 | claude_inject 注入链合并逻辑 + 路径基准 /home/node | M2 runner 注入/采集 | ✅(端到端联调验收后置) | ./DEVPLAN/R3.md |
| R4 | 系统级采集扩展(probe 覆盖 plugin + 路径校准) | M2 runner 注入/采集 | ✅(v2 镜像真机联调后置) | ./DEVPLAN/R4.md |
| R5 | 容器镜像后台可配置(container_image 设置项)+ 默认镜像切 aliyun registry | M1 镜像构建 | ✅(2026-09-28 直做完成:64 测试全绿 + migration 开发库验证;非 rd-dev 流程,补登记) | ./DEVPLAN/R5.md |

(状态:⬜ 未开始 / 🔄 进行中 / ✅ 完成 / ⚠️ 有问题。这张表是**全流程唯一的续接入口**)

## 模块拆分与时间线

| 模块 | 包含需求点 | 依赖 | 预计耗时 | 顺序 |
|---|---|---|---|---|
| M1 镜像构建 | R1, R2 | - | 1d | 1(R1→R2 同一 Dockerfile 顺序改,避免互踩) |
| M2 runner 注入/采集 | R3, R4 | R3 代码独立可先行;R4 验收依赖 R1/R2 新镜像 | 1d | 2(R3→R4) |

## 业务旅程(跨需求点)

| 旅程 | 链路(需求点顺序) | 关键数据传导 |
|---|---|---|
| J1 镜像内置能力 → 系统级可见 | R1+R2 → R4 | 镜像内 /home/node 资产(平台 skills 目录、rd-flow plugin、6 个 MCP 预置配置)被 probe_claude 采集 → claude_system_assets(kind=skill/mcp,plugin 条目 detail.source 标记)→ 系统级列表 + AI 对话 /skills、/mcp 候选(内置徽标) |
| J2 凭据配置 → AI 对话可用 | R2 → R3 | 超管配 7 个 custom_env_vars → 容器创建 env 注入(task_service 铺底,零改动)→ 预置 mcpServers 的 `${VAR}` 展开 → R3 合并语义保证项目级同名覆盖、预置项不被抹 → mysql_dev/beta(只读)/figma server 启动,AI 对话可查库、可读 Figma |

## 范围外

- runner 镜像预装(保持薄代理,PRD 拍板)
- 项目级启用/禁用开关(系统级全局默认可用)
- custom_env_vars 脱敏/加密改造(明文现状沿用)
- 镜像自动构建 CI/版本管理(构建命令进 DEPLOY.md 文档,不建流水线)
- rd-flow plugin 自身功能迭代
- MCP server 运行时外网拉取(D1 禁止)
- 采集自动回采/镜像版本 diff(PRD R4 边界)

## 变更记录

| 日期 | 变更 | 原因 |
|---|---|---|
| 2026-09-27 | 初始版本(R1–R4,继承 ARCH D1–D5) | PRD/ARCH 已确认后 plan 调研 |
| 2026-09-27 | **R1 扩入「平台 skills 目录修正」**:代码精查发现 Dockerfile:33 `COPY skills/` 源指向仓库根 skills/(仅 README 占位),真实 3 个 skill 在 docker/devbox/skills/ 从未进镜像;且平铺 .md 不符 SKILL.md 目录式约定(probe `find -type d` 采不到、CLI 可能不加载)——不修则 R4 验收「平台预装 skills」不成立 | 代码精查新发现(计划外必修) |
| 2026-09-27 | **D5 落地面扩大**:生产常量实为 6 处(ARCH 写 5 处);另有 alembic server_default(f6b9d2e4a1c3:33)需新增 migration 改列默认 + 5 个测试文件硬编码 v1 需同步 | 代码精查勘误 |
| 2026-09-27 | tag v2 的 alembic migration SQL 记入 DEPLOY.md(ARCH 数据模型"无迁移"表述据此修正) | D5 落地需要 |
| 2026-09-27 | server 键名定案:`mysql_dev`/`mysql_beta`/`figma`/`filesystem`/`github`/`brave-search`(PRD R2 描述处「mcp_mysql_dev」按描述性文字处理,正文口径优先;R3 合并/R4 采集/候选均以此键为准) | rd-plan 决策(PRD 前后表述不一致) |
| 2026-09-27 | 不新增 mcp_service.py 内置 mysql/figma 模板(ARCH 标"可选";模板生成键名与预置 server 键不对应,项目级覆盖场景无消费路径) | rd-plan 决策 |
| 2026-09-27 | R2 拟新增 2 个可选变量 ENV_MCP_GITHUB_TOKEN/ENV_MCP_BRAVE_API_KEY——存量 github/brave-search 激活必须有凭据源,PRD 字段表 7 变量未覆盖,否则仅"采集可见"不可用 → 人工确认 | 调研发现规格缺口 |
| 2026-09-27 | R4 plugin skills/commands 落库形态:kind="skill" + detail.source="plugin"(零迁移,PRD 验收 2 直接满足;与 ARCH"表无变更"一致)vs 扩枚举加 command(需迁移+前端改造)→ 人工确认推荐前者 | 调研发现规格缺口(kind 枚举仅 skill/mcp) |
| 2026-09-27 | 实测钉死:rd-flow marketplace name=`rd-flow`(install 目标 `rd-flow@rd-flow`);plugin 落盘 `~/.claude/plugins/cache/<marketplace>/<plugin>/<hash>/`,skills 为分类嵌套 `<分类>/<skill>/SKILL.md`(37 个,deprecated/ 无 SKILL.md);构建期 add/install/list 免登录(空 HOME 沙箱实测) | 选型调研 + 本机验证 |
| 2026-09-27 | 构建类判据(判据 1–4)在开发机无 docker 时降级为 Dockerfile 静态核对,留待有 docker 环境转正(已在 R1 测试验证逻辑注明) | rd-plan 决策(环境约束) |
| 2026-09-27 | **人工确认收口**:① R2 补 2 个可选变量 ENV_MCP_GITHUB_TOKEN/ENV_MCP_BRAVE_API_KEY(变量清单定稿 9 个);② R4 落库形态定稿 kind=skill+detail.source;③ R1 纳入平台 skills 目录修正。DEVPLAN 状态转「已确认」 | 用户拍板(3 项均按推荐方案) |
| 2026-09-27 | R1 开发中:5 个测试文件中 test_container_manager、test_system_assets_read 为入参/seed 回比结构、天然钉不住镜像常量默认值,QA 在其中 3 处补「生产默认值绑定」断言使 Red 可成立——纯增强断言,不改被测行为 | tdd Red 可证性(自主决策) |
| 2026-09-27 | R1 回归发现 2 组与本需求无关的既有失败:① r31/r32 共 20 用例(HEAD 缺 runner_service.validate_tags/update_runner);② test_terminal_manager 1 用例(skipTest 结构缺陷)。证据固定于 .scratch/R1/test-output.md,非 v2 翻转引入,不在 R1 顺手修 | 计划外问题留痕(rd-check 阶段关注) |
| 2026-09-27 | R1 构建冒烟判据 1–4:开发机实测无 docker,按预案降级为 Dockerfile 静态核对(并入审计收口),留待有 docker 环境转正 | 环境约束(DEVPLAN 预案内) |
| 2026-09-27 | R1 审计通过(有条件,0 阻塞):2 Low 已修——F7 四处失效 Red 注释修剪;F8 规格盲区扩入:README.md:54/:118 v1→v2(照抄会产出旧镜像)、frontend TaskDetail.tsx:651 展示标签 devbox:v1→v2(用户可见错标,该文件无其他会话占用;沿「前端文案一致性」技术约定先例)。✅ 状态转正条件:构建冒烟三场景待有 docker 环境补测 | 审计 Low 项处置(自主决策) |
| 2026-09-27 | R3 完成。审计(code-review 双轴)5 发现 0 阻塞:F2/F3/F4/F5 修复;F1 部分采纳——cat 临时故障(readable=False)仅加告警仍按 {} 兜底,审查建议的「跳过写回」不采(会推翻判据 3 与 v1 存量容器并行期兼容两项已确认规格:runner 无法区分「文件不存在」与「临时通道故障」的 cat 失败)。另:R3 会话中 QA subagent 曾虚报测试结果(解释器用错未跑成),已作废并由主 agent 重跑纠正 | 审计 Low 项处置(自主决策) |
| 2026-09-27 | R4 开发中契约微调:probe 响应 `skills` 字段保持「平台 skills」存量语义,新增 `plugin_skills`/`plugin_commands` 两字段承载 plugin 条目(替代分片「skills=平台∪plugin」表述),落库按字段来源打 detail.source="plugin",同名条目自然并列两行 | tdd Red 阶段 QA 发现契约缺口(扁平 ∪ list 无法区分同名条目归属,判据 6 与 source 标记需要来源信息),主 agent 自主决策 |
| 2026-09-28 | **R5 补登记(非 rd-dev 流程,用户直做)**:容器镜像后台可配置——新设置项 `container_image`(vtype image,强制带 tag ≤255);镜像解析链「显式传参 > 设置项 > 常量」落到 schedule_and_start 与 probe collect;默认镜像切 `registry.cn-hangzhou.aliyuncs.com/zhanqinet/devbox:v2`(用户已推送)+ 列默认 migration b4f8e2a9c1d7 + 前端全局参数组字段。64 测试全绿,tsc 通过,migration 开发库 upgrade/downgrade 验证。详见 DEVPLAN/R5.md 与 DEPLOY.md R5 节 | 用户需求直做(2026-09-28 会话) |
| 2026-09-28 | **R1 构建冒烟转正**:docker 环境就绪后实跑三场景全 PASS——A 默认 ARG 构建(镜像 bfd474ce74b2)、B 自定义 ARG 同值、C 不可达 ARG 显式失败(退出码 1,git clone 报错);容器内断言 4/4(skills 3 目录+SKILL.md front-matter、plugin list 含 rd-flow、mcpServers 6 键)。证据 .scratch/R1/smoke-build.md。收口主 agent 直审(零代码 diff 纯验证) | 降级条款到期转正 |
| 2026-09-28 | 冒烟场景 D.d 断言口径修正:mcpServers 校验从「文件插入序」修正为「sort 后集合相等」(与 Dockerfile 构建期断言同口径;JSON 对象键无序,插入序非规格)。首报 FAIL 判定为 QA 断言缺陷,非镜像缺陷 | 自主决策(断言语义) |
