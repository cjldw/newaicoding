# 开发计划:项目详情页聚合改版

> PRD:./PRD.md(已确认,2026-09-29)
> 状态:**已确认**(2026-09-29 人工核对收口:R1 五项口径拍板,R2/R3 自动确认;待确认清单为空)
> 创建日期:2026-09-29
> 调研底稿:.scratch/code-analysis/r1-backend.md(后端接口精查)、r2r3-frontend.md(前端样板解剖)

## 需求概述

项目详情页(`/projects/{id}`)从 5 个平铺 Tab 改为以**聚合概览为默认主视图**:新增项目维度统计接口(R1),概览 Tab 承载四维统计卡 + token + 近 7 天 + 最近需求/任务 Top5(R2),Tab 集收敛为 概览|需求|任务|管理(R3)。完整列表与管理能力零删减,dashboard 个人口径不动。

## 技术约定

(全局一份,分片不重复;rd-dev 全程遵循)

- **后端**:FastAPI + 统一响应 `success(data)`(`{code:0,data,message}`,backend/app/core/response.py:178);鉴权 `get_current_user`(core/auth.py);项目可见三步曲 `get_project_or_404 → get_project_role → _ensure_can_view`;错误抛 `BizError(code, msg, status_code)`
- **聚合先例**:状态零填充 `_by_status_zero_filled` + `REQ_STATUSES`/`TASK_STATUSES`(backend/app/api/dashboard.py:22-49)——从 api.dashboard **导入复用不复制**;查询模式 `select(status, func.count()) + group_by`(dashboard.py:101-105);顺序 await 不 gather(共享 session)
- **前端**:React18 + TS + react-query(queryKey 数组规范:首段资源名+参数);hooks 落 `src/api/projects.ts`;样式走 globals.css 既有类(`.dgrid/.dcard/.kvs/.card/.bdg b-*/.empty/.page-loading`),零新视觉组件;数字 k 缩写工具新建 `src/utils/format.ts`(项目此前无数字格式化);相对时间 `timeAgo` 抽自 NotificationCenter.tsx:39-51
- **枚举口径**:requirement.status / task.status / task.type 全集以 R1 分片「枚举与字典映射」为准;前端徽章文案与色照 TaskDetail VP_ST/VP_TYPE
- **加载态**:项目无骨架屏先例,一律 `.page-loading` 文本态,不引入 Skeleton

## 当前进度

**当前进度: 1/3 (33%) - R1 完成(已提交 c3e4570),正在开发 R2**

| 需求点 | 名称 | 模块 | 状态 | 详情文件 |
|---|---|---|---|---|
| R1 | 项目聚合统计接口 GET /projects/{id}/summary | M1 后端 | ✅ | ./DEVPLAN/R1.md |
| R2 | 概览 Tab(统计区 + 四维区块 + 最近列表) | M2 前端 | ⬜ | ./DEVPLAN/R2.md |
| R3 | Tab 架构调整(概览\|需求\|任务\|管理) | M2 前端 | ⬜ | ./DEVPLAN/R3.md |

(状态:⬜ 未开始 / 🔄 进行中 / ✅ 完成 / ⚠️ 有问题。这张表是**全流程唯一的续接入口**)

## 模块拆分与时间线

| 模块 | 包含需求点 | 依赖 | 预计耗时 | 顺序 |
|---|---|---|---|---|
| M1 后端聚合接口 | R1 | - | 0.5d | 1 |
| M2 前端概览与 Tab | R2, R3 | R1(R2 数据依赖);R3 依赖 R2 | 1d | 2(R2→R3) |

## 业务旅程(跨需求点)

| 旅程 | 链路(需求点顺序) | 关键数据传导 |
|---|---|---|
| J1 项目概览数据链 | R1 → R2 → R3 | R1 summary 单请求产出全部统计数据 → R2 概览区块逐字段消费(四卡/token/近7天/Top5/发布卡)→ R3 把概览设为默认入口;验证点=接口字段↔概览区块一一对应、计数与列表页可对账 |

## 范围外

(PRD「范围外」原样 + 计划明确不做)

- 工作台 dashboard 页(个人口径)与独立任务列表页不改
- 需求/任务详情页不改;移动端适配
- 事件流 activity;效率类指标(二期);逐日图表(二期);自由时间筛选
- 骨架屏组件引入(沿 `.page-loading` 文本态);设置子 Tab URL 深链(沿组件内 state)

## 变更记录

| 日期 | 变更 | 原因 |
|---|---|---|
| 2026-09-29 | 初始版本(R1–R3;无 ARCH 阶段,调研底稿入 .scratch/code-analysis/) | PRD 已确认后 plan 调研 |
| 2026-09-29 | shard-check 格式自检 3/3 通过;语义 5 项主审通过(操作↔接口交叉/异常闭环/权限覆盖/期望覆盖率/负向覆盖 9 域) | 落盘前完备性自检 |
| 2026-09-29 | **人工确认收口**:R1 五项口径用户拍板——①active=需求 polishing+reviewing/任务 pending+running+cases_review ②近 7 天完成=done+updated_at(需求)/finished_at(任务)≥7 天前,阈值 Python 侧算 ③latest_release.branch=work_branch、非 deployed 预览链接置空 ④响应白名单最小化 ⑤枚举扩展须同步 dashboard 常量。**R2/R3 自动确认**(依据:R2 接口复用 R1+纯展示+复用清单非空;R3 纯 Tab 重组零新视觉+组件零改造)。DEVPLAN 状态转「已确认」 | 用户拍板(确认) |
| 2026-09-29 | R1 完成:summary 端点 + build_project_summary + 17 测试用例全绿(py_compile 零错误);审计首审 5 项问题修复闭环、复验条件通过。决策留痕:① requirement.py 的 prd_content/req_branch 判定为「打磨PRD持久化」任务预存改动,保留不回退,仅清除本任务混入的 event/死 import;② project_service.py 的 list_projects BUG-068 为预存改动,代码保留、**提交时与 R1 拆分**;③ conftest.py 回退 HEAD,第二用户场景改测试文件内局部 fixture;④ task.py 整体回退(测试 helper 显式设 created_at 替代 event)。**commit 待用户确认**(全局 git 规则) | /rd-dev R1 |
| 2026-09-29 | 用户全局约束登记:页面 UI/layout 须与现有保持统一——R1 纯后端不适用;**R2/R3 前端需求点必须遵循**(复用 globals.css 既有类,零新视觉组件,与本 DEVPLAN 技术约定一致) | 用户指令(/rd-dev args) |
