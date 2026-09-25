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

**当前进度: 6/6 (100%) - 全部完成(R1.F1/R3.F2 均已 verified)**

| 需求点 | 名称 | 模块 | 状态 | 详情文件 |
|---|---|---|---|---|
| R1 | 手动添加双类型(代码引用/直接创建) | M1 后端+M2 前端 | ✅ | ./DEVPLAN/R1.md |
| R2 | 条目详情页(markdown+代码引用区) | M2 前端+M1 后端 | ✅ | ./DEVPLAN/R2.md |
| R3 | 条目编辑与删除 | M1 后端+M2 前端 | ✅ | ./DEVPLAN/R3.md |
| R4 | 列表摘要与入口修补 | M1 后端+M2 前端 | ✅ | ./DEVPLAN/R4.md |

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
| 2026-09-25 | R2 完成(55bdb49)。审计 B1(editor can_delete 按 R3 口径修正)+S1-S4/S6 修复;顺带修 detail 存量 await-500 与 publish/promote ErrCode NameError 两个存量 bug(在 R2 改造面内)。计划外发现:frontend/src/pages/projects/ProjectTaskList.tsx 存在 tsc 类型错误(并发工作流产物,非本需求范围,不修,留痕) | rd-dev 执行留痕 |
| 2026-09-25 | R1 完成(e171862),审计通过(4 建议留痕)。R3 完成(c0f4246),迁移 e8f4a2c6b9d1 已落开发库(并发流悬空 alembic 版本处置留痕 DEPLOY.md)。R4 完成:QA 链接语法口径严于分片(取链接文字)按 QA 口径实现;审计 P1 归档页形状失配拍板**前端适配后端平铺契约**(后端键名系 R14 存量契约不动),已修复 | rd-dev 执行留痕 |
| 2026-09-25 | 用户反馈「平台知识库页无创建入口」:/knowledge 右上角补「新建条目」按钮(两种 scope 均渲染);平台页创建需先选归属项目,条目仍落项目级——不改变 PRD「平台级直建不做、维持 promote 单通道」边界(后端零改动) | 用户反馈 + 边界澄清 |
| R1.F1 | 修复 BUG-KB-001(平台页创建去向引导) | M2 前端 | ✅ | ./DEVPLAN/R1.F1.md |
| 2026-09-25 | 新增 R1.F1 修复 BUG-KB-001(用户直报:平台页创建成功但列表无记录;分析=UX 断裂,条目已正确入项目列表,方案=成功态+跳转引导,后端零改动) | 用户报告 + rd-fix 分析 |
| 2026-09-25 | R1.F1 完成并 verified(真机回归 11/11:创建→成功态→跳转→列表可见→清理;BUG-KB-001 迁移 ISSUES.md)。另:直接创建空 content 后端 422 为既有校验,留痕不在本 BUG 范围 | rd-fix 回归轮 |
| R3.F2 | 知识条目超管全权限开放 | M1 后端+M2 前端 | ✅ | ./DEVPLAN/R3.F2.md |
| 2026-09-25 | 新增 R3.F2(用户指令「知识条目管理员都开放」):超管不受项目成员限制,条目查看/创建/编辑/删除/发布/提升全通;permissions 增加 can_publish/can_promote 由后端计算(顺带收口 R2 审计遗留的超管提升按钮不可见缺口) | 用户指令 |
| 2026-09-25 | R3.F2 完成:QA 实证后端 get_project_role 的 D16 虚拟 owner 短路已使超管接口层全通(15 用例 13 直接过),实际缺口=permissions 缺 can_publish/can_promote 两键 + 前端按钮本地判断;均已补,三套件 48 passed。「AI 条目仅 tags 白名单」确认不受超管影响(内容治理规则) | rd-fix 执行留痕 |
