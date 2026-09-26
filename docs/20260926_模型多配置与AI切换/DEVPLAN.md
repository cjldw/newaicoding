# 开发计划:模型多配置与 AI 对话切换

> PRD:./PRD.md(已确认,待确认清单清零)
> 状态:**已确认**(2026-09-26;4 项规格确认 + 自动确认清单已过,待确认清零)
> 创建日期:2026-09-26

## 需求概述

平台设置「模型默认配置」升级为「一套 Base URL + API Key + 多个模型名」(tag 风格展示);项目级模型配置升级为「一条配置挂多个模型名」(结构对齐平台);任务详情 AI 对话发送区新增模型选择器(项目配置分组 + 平台默认组),选中后调接口切换并任务级持久,后续消息按所选模型执行(per-exec env 注入覆盖容器固化模型),每条 AI 回复落库并标注所用模型。

## 技术约定

(底账 `knowledge/` 缺失,以下自代码调研得出;rd-dev 全程遵循)

- **响应包装**:统一 `{"code": 0, "data": ..., "message": "ok"}`,错误 code 为业务错误码(`backend/app/core/response.py` ErrCode);前端 `ApiError` 透传 message。
- **错误码**:13xxx 段为模型接入(R13 先例 13001-13004 + 13005 字面量"未配置");平台 LLM 用 2007(不齐备)/2008(连通失败);本次新增 **13006(切换目标不可用)/ 13007(配置组数超上限)/ 13008(模型名数超上限)/ 13009(模型名重复)**,常量登记进 `ErrCode` 并附中文注释。
- **鉴权与角色**:角色 `owner > editor > viewer`(`PROJECT_ROLE_LEVELS`),超管=虚拟 owner,403=1901;配置写操作 `require_project_role(..., "owner")`,读操作 `get_project_role` + internal 可见性回退(模板见 `backend/app/api/projects.py:249-364`)。
- **审计**:`audit_write(db, operator, "<域>.<动作>", project_id=..., target_type=..., target_id=..., detail=...)`,事务内失败不阻塞;detail 禁落 api_key。
- **迁移双轨**:alembic(新迁移 `down_revision='de60f84752af'`)+ `docs/20260920_ai_web开发平台/DEPLOY.md` 追加 DDL 节;MySQL DDL 风格照 R9.F1 样例。
- **platform_settings 多值**:`value` 列为 JSON,数组/对象整体存储(`custom_env_vars` 先例);新键零 DDL。
- **前端**:React+TS+Tailwind+zustand+react-query;shadcn/ui New York(zinc)自绘组件;**禁止引入新依赖**(无 Radix DropdownMenu/Popover);请求封装 `frontend/src/api/`(react-query hooks,queryKey 失效刷新);样式一律复用 `globals.css` 组件类与 tailwind 主题 token(`.chip`/`.input`/`.badge`/`.m-meta`/`bg-popover` 弹层模式),**不得新增视觉体系**。
- **密钥安全**:api_key 全链路 AES-GCM 落盘、接口只回打码(平台:前5+••••••••+后4;项目:前4+***+后4);切换接口只传模型标识不传 key;key 明文不进日志/审计。

## 当前进度

**当前进度: 1/4 (25%) - R1 已完成,下一个 R2**

| 需求点 | 名称 | 模块 | 状态 | 详情文件 |
|---|---|---|---|---|
| R1 | 平台级模型默认配置(一套接入+多模型名 tag) | M3 | ✅ | ./DEVPLAN/R1.md |
| R2 | 项目级模型配置(一条配置挂多模型名) | M3 | ⬜ | ./DEVPLAN/R2.md |
| R3.1 | 对话模型切换后端(切换接口+执行链路+留痕) | M3 | ⬜ | ./DEVPLAN/R3.1.md |
| R3.2 | 对话模型切换前端(选择器+气泡标注) | M3 | ⬜ | ./DEVPLAN/R3.2.md |

(状态:⬜ 未开始 / 🔄 进行中 / ✅ 完成 / ⚠️ 有问题)

## 模块拆分与时间线

| 模块 | 包含需求点 | 依赖 | 预计耗时 | 顺序 |
|---|---|---|---|---|
| M3 AI 能力-平台配置 | R1 | - | 0.5d | 1 |
| M3 AI 能力-项目配置 | R2 | R1(结构对齐,可并行) | 1d | 2 |
| M3 AI 能力-切换后端 | R3.1 | R1, R2 | 1d | 3 |
| M3 AI 能力-切换前端 | R3.2 | R3.1 | 0.5d | 4 |

## 业务旅程(跨需求点)

| 旅程 | 链路(需求点顺序) | 关键数据传导 |
|---|---|---|
| J1 配置→可选→切换→执行→留痕 | R1 → R2 → R3.1 → R3.2 | R1 平台 `llm_models`/`llm_default_model` 与 R2 配置 `models`/`default_model` 被 R3.1 `model-options` 聚合为可选清单;R3.2 选择写 `tasks.chat_config_id/chat_model`;R3.1 消息执行按所选模型 resolve(per-exec env)并把模型名落 `task_messages.model`;R3.2 气泡读该字段标注 |
| J2 所选模型失效→回退→提示 | R2(或 R1)→ R3.1 → R3.2 | R2 删除配置/移除模型名(或 R1 清平台列表)后,R3.1 下一条消息 resolve 失效 → 回退链(default 配置×default_model → 平台默认模型)接管并在响应标 stale/session_reset;R3.2 选择器回显回退结果并提示"原模型已不可用" |

## 范围外

(PRD"范围外"照录)

- 项目级模型配置的整套 Table→tag 改版(仅模型字段 tag 化)
- 平台级多组接入(多套 url+key)
- 模型名自动发现(GET /models 拉取可选列表)
- 用户级/跨任务的模型偏好记忆
- 任务详情以外入口的模型切换
- 模型费用/用量分模型统计
- 任务整体执行/重试所用模型受对话切换影响(切换仅作用于对话消息,PRD Q12 已确认)

## 变更记录

| 日期 | 变更 | 原因 |
|---|---|---|
| 2026-09-26 | (初始版本;R3 拆分为 R3.1 后端 / R3.2 前端) | rd-plan 初稿 |
| 2026-09-26 | 置"已确认";4 项规格按推荐口径确认并回写分片:①服务端测试兜底(R2 create 全量逐测/update 仅测新增);②PUT null/null=清除选择恢复回退链;③model-options/切换接口权限=项目成员(viewer 可,非成员 404),既有端点不收紧;④跨接入切换时主动重置会话(new_session),同接入 resume 失败才走执行期兜底。自动确认清单见核对记录(错误码 13006-13009/迁移双轨/平台零 DDL/UI 全复用现有样式/model 列双写/响应最小化) | 用户回复 continue(批量采纳推荐;如有异议可点名重审) |
| 2026-09-26 | R1 收口:审计通过(3 条观察项不阻塞);完成判据 9/9 ✅;新测试 14/14 绿、存量迁移 10 例、相关单测 72 例 0 failed;ui-check 9/9。提交范围限定 R1 域文件(工作区含非本需求未提交改动,审计改为聚焦式 subagent 而非 code-review 全量双轴) | 常规收口 |
| 2026-09-26 | R1 开发中。实现决策 2 条:①后端——重复模型名 13009 显式拒绝(非静默去重)、空 llm_models 归 2007(未配置=键缺失)、default∉models 归 2007 校验拒绝(2008 仅留给连通失败),与分片文案清单一致;②前端——分片设计规范兜底行的 `text-text-secondary` 为 tailwind 死类(colors.text 非嵌套),按「RelatedUserSelect 同款」既有 token 处理(X=hover:text-red-fg,Star=text-text-muted hover:text-text),已记入 ui-check.md;R23 存量测试按四键口径迁移(改口径不改意图) | tdd 开发中发现,属实现细节口径,不触 PRD 边界 |
