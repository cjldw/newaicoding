# 开发计划:知识条目手动添加与 Markdown 查看

> PRD:./PRD.md(已确认 2026-09-25)
> 创建日期:2026-09-25
> 状态:**已确认**(2026-09-25,人工核对通过,待确认清单为空)

## 需求概述

补全 R14 知识条目体系的手动添加能力:新建 Dialog 升级为「关联代码 / 直接创建」双类型;新增条目详情页(Markdown 渲染 + 代码引用区实时拉取);补条目编辑/删除接口;修补列表摘要与 ArchivePage 空按钮。

## 技术约定

- 后端:FastAPI + SQLAlchemy 2 async,统一响应 `{code,message,data}`,错误码 4 位分域;路由挂 `backend/app/main.py`;权限 `require_project_role(db, project, user, role)` / `require_superadmin`
- GitLab 调用:复用 `gitlab_service.bot_get_file` / `file_service.project_file_content`(平台级 bot token,`get_gitlab_bot_config`);新增分支列表封装
- 前端:原生 fetch 走 `api/client.ts`;样式 globals.css 类体系(.page/.card/.tbl/.btn/.bdg);markdown 统一 `utils/markdown.ts`(本期扩展围栏代码块);代码高亮复用 `components/Editor.tsx` monaco 只读模式
- 数据库:MySQL8,DDL 走 alembic(head=c7d3e9b5a2f4),SQL 全文进 DEPLOY.md

## 当前进度

**当前进度: 1/4 (25%) - R2 已完成,R1 开发中**

| 需求点 | 名称 | 模块 | 状态 | 详情文件 |
|---|---|---|---|---|
| R1 | 手动添加双类型(代码引用/直接创建) | M1 后端+M2 前端 | ⬜ | ./DEVPLAN/R1.md |
| R2 | 条目详情页(markdown+代码引用区) | M2 前端+M1 后端 | ✅ | ./DEVPLAN/R2.md |
| R3 | 条目编辑与删除 | M1 后端+M2 前端 | ⬜ | ./DEVPLAN/R3.md |
| R4 | 列表摘要与入口修补 | M1 后端+M2 前端 | ⬜ | ./DEVPLAN/R4.md |

## 模块拆分与时间线

| 模块 | 包含需求点 | 依赖 | 预计耗时 | 顺序 |
|---|---|---|---|---|
| M1 后端(条目模型/接口) | R1R2R3R4 的后端面 | - | 1d | 1 |
| M2 前端(Dialog/详情页/列表) | R1R2R3R4 的前端面 | M1 接口契约 | 1.5d | 2 |

(R1-R4 前后端交错,建议按 R2(详情+拉取) → R1(创建双型) → R3(编辑删除) → R4(修补) 顺序开发,R2 是数据形态的定义者)

## 业务旅程(跨需求点)

| 旅程 | 链路(需求点顺序) | 关键数据传导 |
|---|---|---|
| J1 代码引用沉淀全流程 | R1 创建(A 型) → R2 详情查看 → R3 编辑/删除 | source_links 的 code 对象在创建写入、详情消费、编辑可改 |
| J2 归档知识消费 | (存量 AI 归档) → R2 详情查看 → R3 标签编辑 | AI 条目仅标签可改,正文锁定 |

## 范围外

- 快照模式(固定 commit)、行区间选择、外部 URL 仓库、平台级直建入口
- 条目版本管理 / 权限细分 / 知识推荐(主 PRD 已定不做)

## 变更记录

| 日期 | 变更 | 原因 |
|---|---|---|
| 2026-09-25 | 初始版本 | PRD 确认后落盘 |
| 2026-09-25 | R2 调整:目录递归树状拉全、单文件不截断、服务端本地缓存 5 分钟 + refresh 穿透;R3 确认 permissions 由后端计算;R1/R3/R4 原样确认 | 人工核对结论 |
